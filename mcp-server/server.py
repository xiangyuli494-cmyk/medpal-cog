"""MedPal-Cog MCP Server

七个工具全部对应赛题要求：
  ingest_asset / get_asset_card      -> R1 多模态资产识别与标识
  kg_query / onto_propose / onto_commit / std_align -> R2 本体半自动构建与标准对齐
  trace_write                        -> R4 跨文档推理与决策链溯源
R3 由「以 MCP 形式暴露给 Nexent + 三个 Skill 包编排」承载。

启动：
  python server.py                     # stdio（本地调试 / MCP Inspector）
  MCP_TRANSPORT=streamable-http python server.py   # HTTP，Nexent 远程链接用
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import parsers
import store
from mcp.server.fastmcp import FastMCP

SERVER_VERSION = "0.1.0"
mcp = FastMCP(
    "medpal-cog",
    instructions=(
        "MedPal-Cog 医疗数据资产认知工具集。所有结论必须携带 asset_id / anchor_id / triple_id，"
        "找不到证据时返回 ok=false 并说明缺口，不得编造。"
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8090")),
    streamable_http_path="/mcp",
    stateless_http=True,
)


def _conn():
    return store.connect(os.environ.get("MEDPAL_DB") or None)


def _ok(**kw):
    kw.setdefault("ok", True)
    return kw


def _err(reason, hint="", **kw):
    out = {"ok": False, "reason": reason, "hint": hint}
    out.update(kw)
    return out


# ---------------- R1 资产 ----------------


@mcp.tool()
def ingest_asset(
    path: str,
    modality: str = "",
    title: str = "",
    source_type: str = "public_standard",
    ingested_by: str = "",
) -> dict:
    """解析一份文件，生成 Asset Card 与可引用锚点，登记入台账。

    返回 asset_id、anchors（每条都可被决策链引用）、解析出的块数与实体。
    modality 留空时按扩展名自动判别：text / pdf_text / table / image_report。
    """
    p = Path(path)
    if not p.exists():
        return _err("file_not_found", "检查路径是否存在：" + path)
    doc = parsers.parse(p)
    if doc is None:
        return _err("no_parser", "该扩展名暂无解析器，请在 parsers.REGISTRY 注册", suffix=p.suffix)
    if doc.metadata.get("error"):
        return _err("parser_unavailable", doc.metadata["error"], path=str(p))

    entities = parsers.guess_entities(doc)
    card = {
        "title": title or doc.title,
        "modality": modality or doc.modality,
        "source": {"type": source_type, "publisher": "", "path": str(p)},
        "version": {"value": "v1", "captured_at": store.now(), "supersedes": None},
        "sensitivity": "public" if source_type == "public_standard" else "synthetic",
        "structure": {
            "blocks": len(doc.blocks),
            "anchors": len(doc.anchors),
            "kinds": sorted({b.kind for b in doc.blocks}),
        },
        "anchors": doc.anchors,
        "entities": entities,
        "kb_status": "ready",
        "ingested_by": ingested_by,
    }
    conn = _conn()
    asset_id = store.upsert_asset(conn, card)
    for a in card["anchors"]:
        a["anchor_id"] = a["anchor_id"].replace(p.stem, asset_id)
    card["asset_id"] = asset_id
    store.upsert_asset(conn, card)
    conn.close()
    return _ok(
        asset_id=asset_id,
        modality=card["modality"],
        anchors=card["anchors"],
        entity_hint=entities,
        blocks=len(doc.blocks),
    )


@mcp.tool()
def get_asset_card(
    asset_id: str = "", modality: str = "", entity: str = "", limit: int = 20
) -> dict:
    """按 asset_id / 模态 / 实体查资产卡片。三个条件都为空时返回最近入库的资产。"""
    conn = _conn()
    try:
        if asset_id:
            card = store.get_asset(conn, asset_id)
            return (
                _ok(cards=[card])
                if card
                else _err("asset_not_found", "先跑 ingest_asset", asset_id=asset_id)
            )
        cards = store.list_assets(conn, modality or None, entity or None, limit)
        return _ok(count=len(cards), cards=cards)
    finally:
        conn.close()


# ---------------- R2 本体 ----------------


@mcp.tool()
def kg_query(
    seed_entities: list[str], max_hops: int = 2, rel_filter: list[str] = None, limit: int = 20
) -> dict:
    """从种子实体出发做多跳本体查询，返回路径与每条边的 provenance。

    路径按「跳数多优先、置信度高优先」排序；未解析的种子会出现在 unresolved 里。
    """
    conn = _conn()
    try:
        return store.kg_query(conn, seed_entities or [], max_hops, rel_filter, limit)
    finally:
        conn.close()


# schema v0 的 8 类关系（docs/ontology-schema.md §3）。写库前必须在这里，否则拒绝。
# `may_cause` 已裁定要加为第 9 类，但要等 schema v1 一起落地（§9 第 3 条），现在只出候选不入库。
SCHEMA_RELS = {
    "has_symptom",
    "diagnosed_by",
    "treated_by",
    "contraindicated_for",
    "requires_exam",
    "belongs_to_dept",
    "subclass_of",
    "aligned_to_standard",
}

# 只允许这三种句式，且头尾必须能被 alias_map 解析成节点——这是「约束输出空间」的落地。
PATTERNS = [
    (
        re.compile(
            r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:患者)?(?:需要做|需要|应做|建议做|须做|需做)"
            r"(?P<tail>[\u4e00-\u9fa5]{2,10}?)(?:检查|检测|试验)"
        ),
        "requires_exam",
    ),
    (
        re.compile(
            r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:可导致|可引起|会导致|可致)(?P<tail>[\u4e00-\u9fa5]{2,12})"
        ),
        "may_cause",
    ),
    (
        re.compile(
            r"(?P<head>[\u4e00-\u9fa5]{2,8}?)(?:禁用|慎用于|禁忌于)(?P<tail>[\u4e00-\u9fa5]{2,8})"
        ),
        "contraindicated_for",
    ),
]
TAIL_SUFFIX = re.compile(r"(等|药物|药品|治疗)$")
ROLE_SUFFIX = re.compile(r"(患者|病人|人群|者|等|药物|药品|治疗|疾病|症状)$")
# 这些关系正反说都指同一件事实，判重时两个方向都要查
REVERSE_TOLERANT = {"contraindicated_for"}


def _alias_of(conn, label: str) -> dict | None:
    """别名表命中：返回 {code, entity_type, scheme}。这是「别名命中」规则的数据源。"""
    row = conn.execute(
        "SELECT code, entity_type, scheme FROM alias WHERE surface = ?", (label,)
    ).fetchone()
    return dict(row) if row else None


@mcp.tool()
def onto_propose(asset_ids: list[str], scope: str = "") -> dict:
    """从给定资产抽取候选三元组，产出待审 diff（不直接写库）。

    低资源策略：约束输出空间——只允许 3 类句式模板、6 类实体、8 类关系；
    规则校验在前（类型匹配、重复、空头尾），通过的才进待审队列。

    候选按**三类规则**分流，每条都带 `kind`，`onto_commit` 按 kind 决定怎么写：

    - `new`：文档里有、本体会没有的关系（含「别名命中」把表面词归一到 canonical id）；
    - `revise`：本体会已有，但这次证据的置信度更高 / 出处更直接 → 修正置信度与 provenance；
    - `deprecate`：**同义关系冲突**——同一 head 同一关系下挂着两个互为别名的 tail，
      只保留一个，另一条提废弃。另外，疾病节点缺 `aligned_to_standard`（**ICD-10 缺对齐**）
      会补一条对齐候选，补不上的进 `unresolved`。
    """
    conn = _conn()
    try:
        cands, rejected = [], []
        known = {r["head_label"] for r in conn.execute("SELECT DISTINCT head_label FROM triple")}
        known |= {r["tail_label"] for r in conn.execute("SELECT DISTINCT tail_label FROM triple")}
        aliases = {r["surface"] for r in conn.execute("SELECT surface FROM alias")}
        vocab = sorted(known | aliases, key=len, reverse=True)

        def expand(text: str, span: tuple) -> str:
            """把正则抓到的片段扩到「覆盖该片段的最长已知实体」。
            例：抓到「消化性溃疡患」，扩成「消化性溃疡」；抓到「幽门螺杆菌呼气」，扩成「幽门螺杆菌呼气试验」。"""
            hs, he = span
            if hs is None or he is None:
                return ""
            for v in vocab:  # 已按长度降序
                idx = text.find(v)
                while idx != -1:
                    if idx <= hs and idx + len(v) >= he:
                        return v
                    idx = text.find(v, idx + 1)
            raw = text[hs:he]
            inner = [v for v in vocab if v in raw]  # 片段内部含已知实体，取最长
            if inner:
                return inner[0]
            return ROLE_SUFFIX.sub("", raw) or raw

        for aid in asset_ids or []:
            card = store.get_asset(conn, aid)
            if not card:
                rejected.append({"asset_id": aid, "reason": "asset_not_found"})
                continue
            for a in card.get("anchors", []):
                text = a.get("text", "")
                if len(text) < 12:
                    rejected.append({"anchor_id": a["anchor_id"], "reason": "too_short"})
                    continue
                hit = False
                for pat, rel in PATTERNS:
                    for m in pat.finditer(text):
                        head = expand(text, m.span("head"))
                        tail = expand(text, m.span("tail"))
                        tail = TAIL_SUFFIX.sub("", tail) or tail
                        if not head or not tail or head == tail or tail in head or head in tail:
                            continue
                        hit = True
                        cands.append(
                            {
                                "head": {"id": "", "type": "Disease", "label": head},
                                "rel": rel,
                                "tail": {
                                    "id": "",
                                    "type": "Exam" if rel == "requires_exam" else "Disease",
                                    "label": tail,
                                },
                                "confidence": 0.72,
                                "provenance": {"asset_id": aid, "anchor_id": a["anchor_id"]},
                            }
                        )
                if not hit:
                    rejected.append({"anchor_id": a["anchor_id"], "reason": "no_pattern_match"})

        kept, seen = [], set()
        for c in cands:
            h_alias = _alias_of(conn, c["head"]["label"])
            t_alias = _alias_of(conn, c["tail"]["label"])
            h = store.resolve_entity(conn, c["head"]["label"])
            t = store.resolve_entity(conn, c["tail"]["label"])
            if not h or not t:
                rejected.append(
                    {
                        "candidate": c["head"]["label"]
                        + "-"
                        + c["rel"]
                        + "->"
                        + c["tail"]["label"],
                        "reason": "entity_unresolved",
                    }
                )
                continue
            # 别名命中：类型与 canonical id 都取别名表的口径，不沿用句式猜的类型
            if h_alias:
                c["head"]["type"] = h_alias["entity_type"]
                c["head"]["via_alias"] = c["head"]["label"]
            if t_alias:
                c["tail"]["type"] = t_alias["entity_type"]
                c["tail"]["via_alias"] = c["tail"]["label"]
            c["head"]["id"], c["tail"]["id"] = h, t

            key = (h, c["rel"], t)
            if key in seen:
                continue
            seen.add(key)

            # 反向表述也视为同一条知识：「疾病患者禁用某药」与「某药禁用于某疾病」
            reverse = 1 if c["rel"] in REVERSE_TOLERANT else 0
            dup = conn.execute(
                "SELECT triple_id, confidence, anchor_id FROM triple WHERE rel=? AND "
                "status='active' AND ((head_id=? AND tail_id=?) OR "
                "(?=1 AND head_id=? AND tail_id=?))",
                (c["rel"], h, t, reverse, t, h),
            ).fetchone()
            if dup:
                # 修正规则：同一事实这次拿到的证据更强（置信度高、或出处更直接）→ 提修正
                better_conf = float(c["confidence"]) > float(dup["confidence"])
                better_src = dup["anchor_id"] != c["provenance"]["anchor_id"]
                if better_conf or better_src:
                    kept.append(
                        {
                            **c,
                            "kind": "revise",
                            "target_triple_id": dup["triple_id"],
                            "confidence": max(float(c["confidence"]), float(dup["confidence"])),
                            "was": {"confidence": dup["confidence"], "anchor_id": dup["anchor_id"]},
                        }
                    )
                else:
                    rejected.append(
                        {
                            "candidate": c["head"]["label"]
                            + "-"
                            + c["rel"]
                            + "->"
                            + c["tail"]["label"],
                            "reason": "duplicate",
                        }
                    )
                continue

            # 同义关系冲突：同一 head 同一关系下已有另一个「互为别名」的 tail
            for row in conn.execute(
                "SELECT triple_id, tail_label, confidence FROM triple "
                "WHERE head_id=? AND rel=? AND status='active' AND tail_id<>?",
                (h, c["rel"], t),
            ).fetchall():
                same = store.align(conn, row["tail_label"])
                if not same.get("ok") or same.get("code") != t:
                    continue
                kept.append(
                    {
                        **c,
                        "kind": "deprecate",
                        "target_triple_id": row["triple_id"],
                        "conflict": {
                            "kept": c["tail"]["label"],
                            "dropped": row["tail_label"],
                            "triple_id": row["triple_id"],
                        },
                        "confidence": max(float(c["confidence"]), float(row["confidence"])),
                    }
                )
                hit_conflict = True
                break
            else:
                hit_conflict = False
            if not hit_conflict:
                kept.append({**c, "kind": "new"})

        # ICD-10 缺对齐：**候选里出现过的**疾病节点只要没有对齐边，就补一条。
        # 注意要从 `cands` 里取而不是 `kept`：同一个病在这些文档里反复出现，
        # 关系本身可能全被判重挡掉（这是正常的），但对齐仍然缺，不能因此漏掉。
        mentioned = {}
        for c in cands:
            for side in ("head", "tail"):
                node = c[side]
                if node.get("type") == "Disease" and node.get("id"):
                    mentioned.setdefault(node["id"], (node, c["provenance"]))
        aligned = {
            r["head_id"]
            for r in conn.execute("SELECT head_id FROM triple WHERE rel='aligned_to_standard'")
        }
        for code, (node, prov) in mentioned.items():
            if code in aligned:
                continue
            if not re.fullmatch(r"[A-Z]\d+(?:\.\d+)?", code):
                rejected.append(
                    {
                        "candidate": node.get("label", ""),
                        "reason": "icd_unmapped",
                        "hint": "疾病节点没有 ICD-10 码，先补 alias 再提对齐",
                    }
                )
                continue
            aligned.add(code)
            kept.append(
                {
                    "kind": "new",
                    "head": {"id": code, "type": "Disease", "label": node["label"]},
                    "rel": "aligned_to_standard",
                    "tail": {
                        "id": "ICD10-" + code,
                        "type": "Disease",
                        "label": "ICD-10 " + code,
                    },
                    "confidence": 0.99,
                    "rule": "icd_missing_alignment",
                    "provenance": prov,
                }
            )

        by_kind = {"new": 0, "revise": 0, "deprecate": 0}
        for c in kept:
            by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1

        diff_id = "DF-" + uuid.uuid4().hex[:8]
        conn.execute(
            "INSERT INTO pending_diff (diff_id,status,payload,created_at) VALUES (?,?,?,?)",
            (diff_id, "pending", json.dumps(kept, ensure_ascii=False), store.now()),
        )
        conn.commit()
        return _ok(
            diff_id=diff_id,
            scope=scope,
            candidates=kept,
            rejected=rejected,
            counts={
                "candidates": len(kept),
                "rejected": len(rejected),
                **{"kind_" + k: v for k, v in by_kind.items()},
            },
        )
    finally:
        conn.close()


@mcp.tool()
def onto_commit(
    diff_id: str = "",
    approve_all: bool = True,
    approve_ids: list[str] = None,
    version: str = "",
    note: str = "",
    to: str = "",
) -> dict:
    """确认待审 diff 并发布新本体版本（version 表 +1、写快照、生成 manifest hash）。

    `to` 非空时改做回滚：不提交 `diff_id`，而是把本体退回到 `to` 指定的已发布版本，
    并照常发布一个新版本（回滚也是一次发布，版本号前进）。回滚只改数据不改历史：
    目标版本里有的三元组复活，目标版本之后新增的标记 `status='removed'` 并记下版本号。
    **回滚不产生待审 diff，`diff_id` 在 `to` 非空时可以不传**——所以它是有默认值的
    位置参数，不是必填。写成必填会让 `onto_commit(to="v1.0")` 在签名层就抛
    TypeError，回滚入口等于不存在。

    候选按 `kind` 写入：`new` 新增、`revise` 修正置信度与出处、`deprecate` 标记废弃。
    schema 之外的 `rel`（如待落地的 `may_cause`）一律跳过并计数，不写进库。
    """
    if to:
        return onto_rollback(target=to, version=version, note=note)
    if not diff_id:
        return _err("diff_id_required", "提交要传 onto_propose 给的 diff_id；回滚传 to")
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM pending_diff WHERE diff_id = ?", (diff_id,)).fetchone()
        if not row:
            return _err("diff_not_found", "先调 onto_propose 生成 diff", diff_id=diff_id)
        items = json.loads(row["payload"])
        if not approve_all and approve_ids:
            items = [c for c in items if c["provenance"]["anchor_id"] in approve_ids]

        cur = store.current_version(conn)
        new_ver = version or _bump(cur["version"] if cur else "v0.9")
        added, revised, deprecated, skipped = 0, 0, 0, 0
        for c in items:
            kind = c.get("kind", "new")
            if kind == "deprecate":
                tid = c.get("target_triple_id")
                row = conn.execute(
                    "SELECT status FROM triple WHERE triple_id = ?", (tid,)
                ).fetchone()
                if row and row["status"] == "active":
                    conn.execute(
                        "UPDATE triple SET status='removed', version_removed=? WHERE triple_id = ?",
                        (new_ver, tid),
                    )
                    deprecated += 1
                continue
            if c.get("rel") not in SCHEMA_RELS:
                skipped += 1
                continue
            if kind == "revise":
                tid = c.get("target_triple_id")
                prov = c.get("provenance", {})
                if tid:
                    conn.execute(
                        "UPDATE triple SET confidence = max(confidence, ?), "
                        "asset_id = coalesce(?, asset_id), anchor_id = coalesce(?, anchor_id) "
                        "WHERE triple_id = ?",
                        (
                            float(c.get("confidence", 0.8)),
                            prov.get("asset_id"),
                            prov.get("anchor_id"),
                            tid,
                        ),
                    )
                    revised += 1
                continue
            if store.add_triple(conn, c, new_ver):
                added += 1
        snap = store.snapshot(conn, new_ver, note or ("from " + diff_id))
        conn.execute("UPDATE pending_diff SET status='committed' WHERE diff_id = ?", (diff_id,))
        conn.commit()
        return _ok(
            diff_id=diff_id,
            version=new_ver,
            added=added,
            revised=revised,
            deprecated=deprecated,
            skipped_not_in_schema=skipped,
            snapshot=snap,
            previous=cur["version"] if cur else None,
        )
    finally:
        conn.close()


def _bump(v: str) -> str:
    m = re.match(r"v(\d+)\.(\d+)", v or "v0.9")
    if not m:
        return "v1.0"
    major, minor = int(m.group(1)), int(m.group(2))
    return "v%d.%d" % (major, minor + 1)


def onto_rollback(target: str = "", version: str = "", note: str = "") -> dict:
    """把本体回滚到某个已发布的版本，并发布一个新版本记录这次回滚。

    由 `onto_commit(to=...)` 调用，不是独立的 MCP 工具——契约固定 10 个工具。

    只回滚数据、不改历史：目标版本的所有活跃三元组重新生效，目标版本之后新增的
    被标记 `status='removed'`（保留版本号，可追）。新版本号默认在当前版本上递增
    （回滚也是一次发布），`note` 写清为什么回。
    """
    conn = _conn()
    try:
        if not target:
            return _err("target_required", "要写回滚到哪个版本，比如 v0.9")
        path = store.DATA_DIR / ("ontology_" + target + ".jsonl")
        if not path.exists():
            return _err(
                "snapshot_not_found", "目标版本的快照文件不存在", target=target, path=str(path)
            )

        wanted = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            wanted[d["triple_id"]] = d

        cur = store.current_version(conn)
        new_ver = version or _bump(cur["version"] if cur else "v0.9")

        # 1) 目标版本里有、当前已被移除的 -> 复活（版本号沿用目标版本的，不伪造新增）
        revived = 0
        for tid in wanted:
            row = conn.execute("SELECT status FROM triple WHERE triple_id = ?", (tid,)).fetchone()
            if row and row["status"] != "active":
                conn.execute(
                    "UPDATE triple SET status='active', version_removed=NULL WHERE triple_id = ?",
                    (tid,),
                )
                revived += 1

        # 2) 当前活跃、但目标版本里没有的 -> 标记移除（保留记录与版本号）
        removed = 0
        for row in conn.execute("SELECT triple_id FROM triple WHERE status='active'").fetchall():
            if row["triple_id"] not in wanted:
                conn.execute(
                    "UPDATE triple SET status='removed', version_removed=? WHERE triple_id = ?",
                    (new_ver, row["triple_id"]),
                )
                removed += 1

        snap = store.snapshot(conn, new_ver, note or ("rollback to " + target))
        conn.commit()
        return _ok(
            version=new_ver,
            target=target,
            revived=revived,
            removed=removed,
            snapshot=snap,
            previous=cur["version"] if cur else None,
        )
    finally:
        conn.close()


@mcp.tool()
def std_align(entity_text: str = "", triple_id: str = "") -> dict:
    """把自由文本实体对齐到 ICD-10 / 临床路径条目；返回对齐方式与置信度。

    对齐失败返回 ok=false 并给出 unmapped 原因，进入待对齐队列。
    """
    conn = _conn()
    try:
        if triple_id:
            row = conn.execute("SELECT * FROM triple WHERE triple_id = ?", (triple_id,)).fetchone()
            if not row:
                return _err("triple_not_found", "检查 triple_id")
            std = json.loads(row["standard_json"] or "{}")
            if std:
                return _ok(triple_id=triple_id, aligned=True, standard=std, source="stored")
            entity_text = row["head_label"]
        if not entity_text:
            return _err("empty_input", "传入 entity_text 或 triple_id")
        res = store.align(conn, entity_text)
        if not res.get("ok"):
            return _err(res.get("reason", "unmapped"), res.get("hint", ""), input=entity_text)
        return _ok(
            input=entity_text,
            aligned=True,
            scheme=res["scheme"],
            code=res["code"],
            match=res["match"],
            confidence=res["confidence"],
        )
    finally:
        conn.close()


# ---------------- R4 溯源 ----------------


@mcp.tool()
def trace_write(
    question: str,
    steps: list[dict],
    agent_version: str = "v1.0",
    elapsed_ms: int = 0,
    gaps: list[str] = None,
) -> dict:
    """写入一次决策链并生成 Markdown 报告，同时计算溯源完整率。

    steps 每项形如 {"i":1,"op":"kg_query","in":[..],"out":[..],
    "evidence":["T-xxx","AST-...#p3.t1.r2"]}。
    """
    if not steps:
        return _err("empty_steps", "至少一步")
    conn = _conn()
    try:
        return store.write_trace(conn, question, steps, agent_version, elapsed_ms, gaps)
    finally:
        conn.close()


@mcp.tool()
def skill_export(trace_id: str, name: str = "") -> dict:
    """把一条成功 trace 导出成 Nexent Skill 模板草稿（SKILL.md 片段）。"""
    conn = _conn()
    try:
        t = store.get_trace(conn, trace_id)
        if not t:
            return _err("trace_not_found", "检查 trace_id")
        tools_used = []
        for s in t["steps"]:
            op = s.get("op")
            if (
                op
                and op not in tools_used
                and op not in {"entity_extract", "conclude", "conflict_check"}
            ):
                tools_used.append(op)
        body = [
            "---",
            "name: " + (name or ("auto-" + trace_id.lower())),
            "description: 由 trace "
            + trace_id
            + " 自动导出，覆盖步骤 "
            + str(len(t["steps"]))
            + " 步",
            "allowed-tools: [" + ", ".join(tools_used) + "]",
            "tags: [auto-exported, medical]",
            "---",
            "",
            "## 何时用",
            "问题形态与「" + t["question"][:40] + "」相近时。",
            "",
            "## 步骤",
        ]
        for s in t["steps"]:
            body.append("{}. {} -> {}".format(s.get("i"), s.get("op"), str(s.get("out", ""))[:80]))
        body += ["", "## 禁止", "- 引用无 anchor_id 的内容", "- 给出药品剂量"]
        return _ok(trace_id=trace_id, skill_md="\n".join(body), tools=tools_used)
    finally:
        conn.close()


@mcp.tool()
def kb_search(query: str, top_k: int = 5, mode: str = "hybrid") -> dict:
    """透传 Nexent 知识库检索（未配置 KB_ENDPOINT 时返回配置提示）。"""
    endpoint = os.environ.get("KB_ENDPOINT", "")
    if not endpoint:
        return _err(
            "kb_not_configured",
            "设置 KB_ENDPOINT 后由 Nexent 混合检索承担；否则直接用平台 search-knowledge-base 技能",
            query=query,
        )
    return _ok(
        query=query, mode=mode, top_k=top_k, results=[], note="stub：接入 Nexent /knowledge 接口"
    )


@mcp.tool()
def health() -> dict:
    """健康检查：返回版本、库路径、三元组数与当前本体版本。"""
    conn = _conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM triple WHERE status='active'").fetchone()["c"]
        a = conn.execute("SELECT COUNT(*) c FROM asset").fetchone()["c"]
        cur = store.current_version(conn)
        return _ok(
            server_version=SERVER_VERSION,
            triples=n,
            assets=a,
            ontology_version=cur["version"] if cur else None,
            db=str(store.DB_PATH),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    t0 = time.time()
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
