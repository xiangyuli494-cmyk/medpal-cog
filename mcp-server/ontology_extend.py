"""从表格与指南 PDF 里长本体 v1.0：只读文档写明的关系，不做自由生成。

与 `ontology_grow.py` 的分工：
- `grow`：pathway_01..04 摘要 → 疾病 / 科室 / 检查 / ICD，长出来的是 **v0.9 = 37 条**。
  那是冻结基线，本模块不动它。
- 本模块：**其余样例文档**里写着、但 v0.9 没人抽过的关系，产出 **v1.0**：
  1. `pdf_02_table` 的检查项目表：首选检查 / 次选检查 / 禁忌三列。
  2. `pdf_01` `pdf_03` `pdf_04` `pdf_05` 指南正文：「以某检查确诊」「首选药物」两句。
  3. `pathway_05..20`：`grow` 只读前 4 份，第 5 份起才会出现的新检查项。

三条硬约束，写在这里防止后来人绕过去：

1. **只产出 schema v0 的 8 类关系**（`docs/ontology-schema.md` §3）。表里的「次选检查」与
   正文的「以某检查确诊」都归到 `requires_exam`——语义就是「该病要做该检查」，首选/次选
   用 confidence 区分（0.95 / 0.80 / 0.85）。**不新造 `requires_exam_alt`、`diagnosed_by_exam`、
   `subtype_of` 这类 schema 之外的关系名**：加关系类是结构变更，要走 schema §11 的裁决流程，
   不是抽取脚本说了算。
2. **疾病节点只收能落到 ICD-10 码的**。schema §2.1 规定 Disease 的 ID 就是 ICD-10 码；文档没给
   码的病名（如「幽门螺杆菌感染」「十二指肠溃疡」）留在 `unresolved` 里等对齐，不许临时编一个
   `DIS-<hash>` 号塞进图——那会造出检索得到、但对不上标准的节点。
3. **禁忌列只收能解析成药物的值**。`pdf_02` 第 3 行的禁忌是「近期服用PPI」，那是「做这项检查
   的前提条件」，不是「某药禁用于某病」；解析不出药物就整条丢掉并记进 `unresolved`。

每条三元组的 provenance 都指回具体锚点，`kg_query` 与决策链能直接引。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import store

ROOT = Path(__file__).resolve().parent.parent

# 表头 -> (关系, 置信度)。次选检查仍进 requires_exam，靠置信度表达强度（见模块 docstring 第 1 条）。
COLUMN_REL = {
    "首选检查": ("requires_exam", 0.95),
    "次选检查": ("requires_exam", 0.80),
    "禁忌": ("contraindicated_for", 0.80),
}

# 检查项的书写变体 -> 已登记的 canonical **写法**（再经 EXAM_IDS 拿到编号）。
# 值必须是 EXAM_IDS 的键；直接写 `EX-` 编号会让下面 `label in EXAM_IDS` 落空，
# 最后按哈希兜底，长出一个谁也不认识的重复节点（K27 会同时连到 胃镜 和 内镜检查）。
# 不收上位概念（「幽门螺杆菌检测」是呼气试验/活检的统称，另建节点而不是并进 EX-HP-BT）。
EXAM_SYNONYMS = {"内镜检查": "胃镜", "胃镜检查": "胃镜", "呼气试验": "幽门螺杆菌呼气试验"}

EXAM_IDS = {
    "血压监测": "EX-BP-MON",
    "心电图": "EX-ECG",
    "肾功能": "EX-RENAL",
    "空腹血糖": "EX-FPG",
    "糖化血红蛋白": "EX-HBA1C",
    "眼底检查": "EX-FUNDUS",
    "胸片": "EX-CXR",
    "血常规": "EX-CBC",
    "C反应蛋白": "EX-CRP",
    "泌尿系超声": "EX-US-KUB",
    "尿常规": "EX-URINE",
    "胃镜": "EX-GASTRO",
    "幽门螺杆菌呼气试验": "EX-HP-BT",
}

# 「X 检查是确诊 Y 的主要方法」
DIAGNOSED_BY = re.compile(
    r"(?P<exam>[A-Za-z\u4e00-\u9fa5]{2,10}?检查)(?:可|是|可作为)(?:确诊|诊断)"
    r"(?P<disease>[\u4e00-\u9fa5]{2,10}?)(?:的)?(?:主要|首选|重要)方法"
)
# 「X 是治疗 Y 的首选药物」
FIRST_LINE_DRUG = re.compile(
    r"(?P<drug>[\u4e00-\u9fa5A-Za-z0-9]{2,14})(?:是|可作为)治疗"
    r"(?P<disease>[\u4e00-\u9fa5]{2,10})的(?:首选|一线)"
)
ICD_IN_TEXT = re.compile(r"([\u4e00-\u9fa5]{2,10})（ICD-10\s*([A-Z]\d+(?:\.\d+)?)）")


def _slug(prefix: str, label: str) -> str:
    return prefix + hashlib.sha1(label.encode()).hexdigest()[:6]


def _exam_id(conn, label: str) -> tuple[str, bool]:
    """返回 (id, 是否已有节点)。先归一同义写法，再查库，最后按名字哈希兜底。"""
    label = EXAM_SYNONYMS.get(label, label)
    if label in EXAM_IDS:
        return EXAM_IDS[label], True
    hit = _typed_id(conn, label, "Exam")
    return (hit, True) if hit else (_slug("EX-", label), False)


def _typed_id(conn, label: str, want: str) -> str | None:
    """**按类型**解析实体：只接受 `want` 类型的节点，找不到就返回 None。

    不能用 `store.resolve_entity`：它内部走 `store.align` 的包含匹配
    （`? LIKE '%' || surface || '%'`），「幽门螺杆菌感染」会被匹配到别名
    「幽门螺杆菌」→ `EX-HP-BT`。那是检查项，而「幽门螺杆菌感染」是疾病——
    这个模糊匹配会让 `requires_exam` 长出「检查 → 检查」这种 schema §3.1 明令禁止的边。

    先查三元组里已经确立的类型（head/tail 两侧都要看），再查别名表的 entity_type。
    """
    label = (label or "").strip()
    if not label:
        return None
    row = conn.execute(
        "SELECT head_id i FROM triple WHERE head_label=? AND head_type=? "
        "UNION SELECT tail_id i FROM triple WHERE tail_label=? AND tail_type=? LIMIT 1",
        (label, want, label, want),
    ).fetchone()
    if row:
        return row["i"]
    row = conn.execute(
        "SELECT code FROM alias WHERE surface=? AND entity_type=? LIMIT 1", (label, want)
    ).fetchone()
    return row["code"] if row else None


def _disease_id(conn, label: str) -> str | None:
    """疾病只认能在库里落地的——不新建没有 ICD-10 码的疾病节点（docstring 第 2 条）。

    还要求 ID 是 ICD-10 形态：`docs/ontology-schema.md` §2.1 规定 Disease 的 ID 就是
    ICD-10 码，`EX-`/`DEP-` 这类前缀一定不是疾病。
    """
    code = _typed_id(conn, label, "Disease")
    if not code or not re.fullmatch(r"[A-Z]\d+(?:\.\d+)?", code):
        return None
    return code


# schema §3 的强制类型约束：写库前必须过这一关，只靠抽取侧「有意写成 Disease」不算数。
REL_TYPES = {
    "has_symptom": ({"Disease"}, {"Symptom"}),
    "diagnosed_by": ({"Symptom"}, {"Disease"}),
    "treated_by": ({"Disease"}, {"Drug"}),
    "contraindicated_for": ({"Drug"}, {"Disease"}),
    "requires_exam": ({"Disease"}, {"Exam"}),
    "belongs_to_dept": ({"Disease", "Symptom"}, {"Department"}),
    "subclass_of": ({"Disease"}, {"Disease"}),
    "aligned_to_standard": ({"Disease"}, {"Disease", "Finding"}),
}


def _add(conn, head, rel, tail, confidence, asset_id, anchor_id, version, stats, note=""):
    if not head or not tail or head["id"] == tail["id"] or head["label"] == tail["label"]:
        return False
    # schema §3.1：头尾类型错了不是「数据质量问题」，是写坏了。挡在这里，别等下游发现。
    want = REL_TYPES.get(rel)
    if not want:
        stats["unresolved"].append(f"{rel} 不在 schema 的 8 类关系里，拒收")
        return False
    if head["type"] not in want[0] or tail["type"] not in want[1]:
        stats["unresolved"].append(
            f"{head['label']}({head['type']}) -[{rel}]-> {tail['label']}({tail['type']}) "
            f"类型不合 schema（应为 {sorted(want[0])} → {sorted(want[1])}），拒收"
        )
        return False
    tid = store.add_triple(
        conn,
        {
            "head": head,
            "rel": rel,
            "tail": tail,
            "confidence": confidence,
            "provenance": {"asset_id": asset_id, "anchor_id": anchor_id},
            "standard": {},
        },
        version=version,
    )
    if tid:
        stats["triples"] += 1
        stats["added"].append(
            {
                "triple_id": tid,
                "text": f"{head['label']} -[{rel}]-> {tail['label']}",
                "note": note,
                "anchor_id": anchor_id,
            }
        )
        return True
    stats["duplicate"] += 1
    return False


def _cells(text: str) -> list[str]:
    """表格行文本是 `a | b | c`，拆成单元格。"""
    return [c.strip() for c in text.split("|")]


def grow_from_tables(conn, version: str, stats: dict) -> None:
    """pdf_02 那张「疾病名称 | 首选检查 | 次选检查 | 禁忌」表。"""
    rows = conn.execute(
        "SELECT asset_id FROM asset WHERE modality='pdf_text' AND title LIKE '%table%'"
    ).fetchall()
    for row in rows:
        card = store.get_asset(conn, row["asset_id"])
        if not card:
            continue
        header = None
        for a in card.get("anchors") or []:
            cells = _cells(a.get("text", ""))
            if "疾病名称" in cells:
                header = {name: cells.index(name) for name in COLUMN_REL if name in cells}
                header["疾病名称"] = cells.index("疾病名称")
                continue
            if not header or len(cells) < 3:
                continue
            name_idx = header.get("疾病名称")
            if name_idx is None or name_idx >= len(cells):
                continue
            disease_label = cells[name_idx]
            disease_id = _disease_id(conn, disease_label)
            if not disease_id:
                stats["unresolved"].append(
                    f"{row['asset_id']}#{a['anchor_id'].split('#')[-1]}: "
                    f"病名「{disease_label}」没有 ICD-10 码，等对齐"
                )
                continue
            head = {"id": disease_id, "type": "Disease", "label": disease_label}
            for col, (rel, conf) in COLUMN_REL.items():
                idx = header.get(col)
                if idx is None or idx >= len(cells):
                    continue
                value = cells[idx]
                if not value or value in ("无", "—", "-"):
                    continue
                if rel == "contraindicated_for":
                    drug = store.resolve_entity(conn, value)
                    if not drug:
                        stats["unresolved"].append(
                            f"{row['asset_id']}#{a['anchor_id'].split('#')[-1]}: "
                            f"禁忌「{value}」不是药物，不收"
                        )
                        continue
                    tail = {"id": drug, "type": "Drug", "label": value}
                else:
                    exam_id, existed = _exam_id(conn, value)
                    if not existed:
                        stats["unresolved"].append(f"新检查项：{value} → {exam_id}")
                    tail = {"id": exam_id, "type": "Exam", "label": value}
                _add(
                    conn,
                    head,
                    rel,
                    tail,
                    conf,
                    row["asset_id"],
                    a["anchor_id"],
                    version,
                    stats,
                    note=col,
                )


def grow_from_guide(conn, version: str, stats: dict) -> None:
    """指南正文：以某检查确诊、首选药物。只认写明了病名的句子。"""
    rows = conn.execute(
        "SELECT asset_id FROM asset WHERE modality='pdf_text' AND title NOT LIKE '%table%'"
    ).fetchall()
    for row in rows:
        card = store.get_asset(conn, row["asset_id"])
        if not card:
            continue
        for a in card.get("anchors") or []:
            text = a.get("text", "")
            if len(text) < 12:
                continue
            for m in DIAGNOSED_BY.finditer(text):
                disease = m.group("disease")
                did = _disease_id(conn, disease)
                if not did:
                    stats["unresolved"].append(
                        f"{row['asset_id']}: 病名「{disease}」没有 ICD-10 码，等对齐"
                    )
                    continue
                exam_label = m.group("exam")
                exam_id, _ = _exam_id(conn, exam_label)
                _add(
                    conn,
                    {"id": did, "type": "Disease", "label": disease},
                    "requires_exam",
                    {"id": exam_id, "type": "Exam", "label": exam_label},
                    0.85,
                    row["asset_id"],
                    a["anchor_id"],
                    version,
                    stats,
                    note="确诊方法",
                )
            for m in FIRST_LINE_DRUG.finditer(text):
                disease = m.group("disease")
                did = _disease_id(conn, disease)
                if not did:
                    continue
                drug = m.group("drug")
                _add(
                    conn,
                    {"id": did, "type": "Disease", "label": disease},
                    "treated_by",
                    {"id": _slug("DRUG-", drug), "type": "Drug", "label": drug},
                    0.85,
                    row["asset_id"],
                    a["anchor_id"],
                    version,
                    stats,
                    note="首选药物",
                )


def grow_from_pathways(conn, version: str, stats: dict, start: int = 5, end: int = 20) -> None:
    """pathway_05..20：`grow` 只读了前 4 份，后面的摘要里还有没抽过的检查项。

    读法与 `ontology_grow.grow` 一致（诊断依据给 ICD 与科室，检查项目给检查项），
    只补库里还没有的边，已有的由 `add_triple` 判重挡掉。
    """
    for i in range(start, end + 1):
        path = ROOT / f"data/samples/text/pathway_{i:02d}.md"
        if not path.exists():
            continue
        card = conn.execute(
            "SELECT asset_id, anchors_json FROM asset WHERE source_json LIKE ? LIMIT 1",
            (f"%{path.name}%",),
        ).fetchone()
        if not card:
            stats["unresolved"].append(f"pathway_{i:02d}: 台账里没有这份文档的资产卡")
            continue
        anchors = json.loads(card["anchors_json"] or "[]")
        # ICD 码写在「诊断依据」那句里，不在标题里（标题只有病名）
        diag_anchor = next((a for a in anchors if "ICD-10" in a.get("text", "")), None)
        if not diag_anchor:
            stats["unresolved"].append(f"pathway_{i:02d}: 诊断依据里没有 ICD-10 码")
            continue
        icd = ICD_IN_TEXT.search(diag_anchor["text"])
        if not icd:
            continue
        disease_label = icd.group(1).strip()
        exam_anchor = next(
            (a for a in anchors if a.get("kind") == "sentence" and a["text"].count("、") >= 2),
            None,
        )
        if not exam_anchor:
            continue
        head = {"id": icd.group(2), "type": "Disease", "label": disease_label}
        for name in [x.strip() for x in exam_anchor["text"].rstrip("。").split("、") if x.strip()]:
            exam_id, existed = _exam_id(conn, name)
            if not existed:
                stats["unresolved"].append(f"新检查项：{name} → {exam_id}")
            _add(
                conn,
                head,
                "requires_exam",
                {"id": exam_id, "type": "Exam", "label": name},
                0.85,
                card["asset_id"],
                exam_anchor["anchor_id"],
                version,
                stats,
                note="检查项目",
            )


def grow_from_dept_lines(conn, version: str, stats: dict) -> None:
    """pathway 摘要的「诊断依据」句同时写明科室：「X（ICD-10 K27），就诊科室 消化内科」。

    `ontology_grow.grow` 只在**前 4 份**里抽这条边，`pathway_05..20` 里同一批疾病
    还有科室没进库的（K27 在第 5 份首次出现，是 v0.9 里少掉的那条）。
    这条边有原文、有锚点，是「文档写明的关系」，不是补数据。
    """
    for i in range(1, 21):
        path = ROOT / f"data/samples/text/pathway_{i:02d}.md"
        if not path.exists():
            continue
        card = conn.execute(
            "SELECT asset_id, anchors_json FROM asset WHERE source_json LIKE ? LIMIT 1",
            (f"%{path.name}%",),
        ).fetchone()
        if not card:
            continue
        anchors = json.loads(card["anchors_json"] or "[]")
        diag = next((a for a in anchors if "就诊科室" in a.get("text", "")), None)
        if not diag:
            continue
        icd = ICD_IN_TEXT.search(diag["text"])
        dept_m = re.search(r"就诊科室\s*([^\s，。,]+)", diag["text"])
        if not icd or not dept_m:
            continue
        dept_label = dept_m.group(1).strip()
        dept_id = _typed_id(conn, dept_label, "Department") or _slug("DEP-", dept_label)
        _add(
            conn,
            {"id": icd.group(2), "type": "Disease", "label": icd.group(1).strip()},
            "belongs_to_dept",
            {"id": dept_id, "type": "Department", "label": dept_label},
            0.9,
            card["asset_id"],
            diag["anchor_id"],
            version,
            stats,
            note="诊断依据:科室",
        )


def _symptom_ids(conn, token: str) -> list[str]:
    """把一段症状表面词解析成节点 id 列表；解析不出来返回空列表。

    先整体解析（「上腹隐痛」是一个词），整体落不到节点时再按**已知别名的最长匹配**
    从左到右切（「反酸烧心」= 「反酸」+「烧心」）。

    为什么不能只按 `、` 和「和」切：`test_guide_01` 原文是
    「患者出现上腹隐痛、反酸烧心症状，建议及时就诊」——`反酸烧心` 里没有顿号，
    按标点切会把它当成一个整体词，`_typed_id` 查不到就整条丢掉。那句是**就诊指南
    唯一写着症状归口的话**，丢掉它等于「反酸烧心该挂消化内科」进不了图，
    而分诊正是 eval 里 H001/Q017/Q020/Q023 要考的能力。
    """
    whole = _typed_id(conn, token, "Symptom")
    if whole:
        return [whole]
    surfaces = [
        r["surface"]
        for r in conn.execute(
            "SELECT surface FROM alias WHERE entity_type='Symptom' ORDER BY length(surface) DESC"
        )
    ]
    out, i = [], 0
    while i < len(token):
        for surface in surfaces:
            if surface and token.startswith(surface, i):
                sid = _typed_id(conn, surface, "Symptom")
                if sid and sid not in out:
                    out.append(sid)
                i += len(surface)
                break
        else:
            return []  # 有切不动的字，说明整句不是纯症状串，不强行猜
    return out


def _label_of(conn, sid: str, fallback: str) -> str:
    """节点的中文正名：优先用库里已有的 label，查不到才回退到文档里的表面词。

    切词切出来的表面词（「反酸」）和节点正名（「烧心」）不一定相同——别名表里
    两者都指向 `SYM-HEART`。schema §2.2 要求 `head_label` 存中文正名，所以
    这里必须取库里的，不能拿表面词当 label。
    """
    row = conn.execute(
        "SELECT head_label l FROM triple WHERE head_id=? AND head_type='Symptom' "
        "UNION SELECT tail_label FROM triple WHERE tail_id=? AND tail_type='Symptom' LIMIT 1",
        (sid, sid),
    ).fetchone()
    if row and row["l"]:
        return row["l"].lstrip("#").strip()
    row = conn.execute("SELECT surface FROM alias WHERE code=? LIMIT 1", (sid,)).fetchone()
    return row["surface"] if row and row["surface"] else fallback


def grow_from_guides(conn, version: str, stats: dict) -> None:
    """就诊指南类文档：症状归口到科室、症状属于某病。

    两条都在文档里写死了：
    - 「第一章 消化内科就诊指南」+「患者出现上腹隐痛、反酸烧心症状，建议及时就诊」
      → 症状 `belongs_to_dept` 该科室（分诊要用的知识，schema §3.1 明确允许 Symptom 当头）。
    - 「上腹部疼痛是本病的主要症状」→ 该文档讲的病 `has_symptom` 该症状。
    """
    # ① 就诊指南：标题给出科室，正文给出症状清单
    rows = conn.execute(
        "SELECT asset_id FROM asset WHERE modality='pdf_text' AND title LIKE '%guide%'"
    ).fetchall()
    for row in rows:
        card = store.get_asset(conn, row["asset_id"])
        if not card:
            continue
        anchors = card.get("anchors") or []
        dept_label = None
        for a in anchors:
            m = re.search(r"([\u4e00-\u9fa5]{2,8}科)就诊指南", a.get("text", ""))
            if m:
                dept_label = m.group(1)
                break
        if not dept_label:
            continue
        dept_id = _typed_id(conn, dept_label, "Department") or _slug("DEP-", dept_label)
        for a in anchors:
            text = a.get("text", "")
            if "症状" not in text or "就诊" not in text:
                continue
            # 「上腹隐痛、反酸烧心症状」→ 拆出一个个症状名
            m = re.search(r"出现([^。，]*?)症状", text)
            if not m:
                continue
            for name in [x.strip() for x in re.split(r"[、和]", m.group(1)) if x.strip()]:
                sids = _symptom_ids(conn, name)
                if not sids:
                    stats["unresolved"].append(f"症状「{name}」没有节点，等归一")
                    continue
                for sid in sids:
                    _add(
                        conn,
                        {"id": sid, "type": "Symptom", "label": _label_of(conn, sid, name)},
                        "belongs_to_dept",
                        {"id": dept_id, "type": "Department", "label": dept_label},
                        0.85,
                        row["asset_id"],
                        a["anchor_id"],
                        version,
                        stats,
                        note="就诊指南:症状归口",
                    )

    # ② 指南正文：「X 是本病/该病的主要症状」，头取该文档标题里的疾病
    rows = conn.execute(
        "SELECT asset_id, title FROM asset WHERE modality='pdf_text' AND title NOT LIKE '%table%'"
    ).fetchall()
    for row in rows:
        card = store.get_asset(conn, row["asset_id"])
        if not card:
            continue
        had = None
        for a in card.get("anchors") or []:
            for code, label in _disease_labels(conn):
                if label and label in row["title"]:
                    had = (code, label)
                    break
            if had:
                break
        if not had:
            continue
        for a in card.get("anchors") or []:
            text = a.get("text", "")
            m = re.search(r"([\u4e00-\u9fa5]{2,10})是本病(?:的)?(?:主要)?症状", text)
            if not m:
                m = re.search(r"([\u4e00-\u9fa5]{2,10})是本病", text)
            if not m:
                continue
            name = m.group(1).strip()
            sid = _typed_id(conn, name, "Symptom")
            if not sid:
                stats["unresolved"].append(f"症状「{name}」没有节点，等归一")
                continue
            _add(
                conn,
                {"id": had[0], "type": "Disease", "label": had[1]},
                "has_symptom",
                {"id": sid, "type": "Symptom", "label": name},
                0.85,
                row["asset_id"],
                a["anchor_id"],
                version,
                stats,
                note="主要症状",
            )


def _disease_labels(conn) -> list[tuple[str, str]]:
    """库里已有的疾病节点 (id, label)，label 去掉「# 」前缀（那是标题标记，不是名字的一部分）。"""
    out = []
    for r in conn.execute(
        "SELECT DISTINCT head_id i, head_label l FROM triple WHERE head_type='Disease' "
        "UNION SELECT DISTINCT tail_id i, tail_label l FROM triple WHERE tail_type='Disease'"
    ):
        label = (r["l"] or "").lstrip("#").strip()
        if label and not label.startswith("ICD-10"):
            out.append((r["i"], label))
    return out


def grow(conn, version: str = "v1.0") -> dict:
    stats: dict = {"triples": 0, "duplicate": 0, "unresolved": [], "added": []}
    grow_from_tables(conn, version, stats)
    grow_from_guide(conn, version, stats)
    grow_from_pathways(conn, version, stats)
    grow_from_dept_lines(conn, version, stats)
    grow_from_guides(conn, version, stats)
    conn.commit()
    return stats