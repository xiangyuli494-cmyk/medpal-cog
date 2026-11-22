import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples"
CARDS = ROOT / "data" / "asset-cards"
# 与 server/store 的口径对齐：容器里 MEDPAL_DB 指到卷上的库，这里也得跟着走，
# 否则「灌进 A 库、服务读 B 库」，asset 数永远是 0。
DB = Path(os.environ.get("MEDPAL_DB") or ROOT / "mcp-server" / "data" / "medpal.db")
sys.path.insert(0, str((ROOT / "mcp-server").resolve()))
import server  # noqa: E402


def business_title(path: Path) -> str:
    """给台账一个像样的标题：md 取一级标题，其余按类型给中文名并带序号。"""
    if path.suffix.lower() == ".md":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()[:60]
    stem = path.stem
    num = "".join(ch for ch in stem if ch.isdigit())
    label = {
        "bingli": "合成门诊病历",
        "menzhen": "门诊记录",
        "pathway": "临床路径摘要",
        "reference": "检验参考区间",
    }.get(stem.split("_")[0], stem)
    return f"{label} {num}".strip() if num else label


def _strip_ts(card: dict) -> dict:
    """去掉时间戳后再比较：内容没变就不该刷新 captured_at/created_at。"""
    c = json.loads(json.dumps(card))
    c.pop("created_at", None)
    if isinstance(c.get("version"), dict):
        c["version"].pop("captured_at", None)
    return c


def main() -> int:
    samples = sorted(p for p in SAMPLES.rglob("*") if p.is_file())
    # 0 份样本不算「成功」：以前这里照样返回 0，于是 entrypoint 的 `|| exit 1` 永远不触发，
    # 容器带着空台账起服务、healthcheck 还说健康（评审 #36 第 3 条）。
    if not samples:
        print(f"样本 0 份（{SAMPLES} 是空的），不做空账，返回 1")
        return 1

    # 先记住旧卡的 {asset_id: card}：重跑时内容没变就沿用旧时间戳，否则每跑一次台账就脏一次
    old_cards = {}
    for f in CARDS.glob("*.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("asset_id"):
            old_cards[c["asset_id"]] = c
    # 幂等：清空台账再入库，避免重复 ingest 翻倍
    con = sqlite3.connect(str(DB))
    con.execute("delete from asset")
    con.commit()
    con.close()

    mapping = {}
    for path in samples:
        res = server.ingest_asset(
            path=str(path), source_type="synthetic", ingested_by="T5", title=business_title(path)
        )
        if res.get("asset_id"):
            mapping[path.name] = res.get("modality") or "?"

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute("select * from asset order by created_at desc").fetchall()
    con.close()

    # 全部解析失败也要喊出来：0 行时若继续往下走会把旧卡删光，等于把台账清空还报成功。
    if not rows:
        print(f"入库 0 行（{len(samples)} 份样本全部解析失败），保留原台账，返回 1")
        return 1

    for old in CARDS.glob("*.json"):
        old.unlink()
    for r in rows:
        card = {
            "asset_id": r["asset_id"],
            "title": r["title"],
            "modality": r["modality"],
            "source": json.loads(r["source_json"] or "{}"),
            "version": json.loads(r["version_json"] or "{}"),
            "sensitivity": r["sensitivity"],
            "structure": json.loads(r["structure_json"] or "{}"),
            "anchors": json.loads(r["anchors_json"] or "[]"),
            "entities": json.loads(r["entities_json"] or "[]"),
            "kb": {"base": "med-text", "doc_id": "", "status": r["kb_status"] or "ready"},
            "ingested_by": r["ingested_by"],
            "created_at": r["created_at"],
        }
        prev = old_cards.get(card["asset_id"])
        if prev and _strip_ts(prev) == _strip_ts(card):
            card["created_at"] = prev.get("created_at", card["created_at"])
            if isinstance(card.get("version"), dict) and isinstance(prev.get("version"), dict):
                card["version"]["captured_at"] = prev["version"].get(
                    "captured_at", card["version"].get("captured_at")
                )
        (CARDS / f"{card['asset_id']}.json").write_text(
json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8",
            newline="\n",
        )

    print(f"样本 {len(samples)} 份 | 入库 {len(rows)} 行 | 导出 {len(rows)} 张卡")
    per_dir = {}
    for path in samples:
        per_dir[path.parent.name] = per_dir.get(path.parent.name, 0) + 1
    print("  按目录:", per_dir)
    per_mod = {}
    for name, m in mapping.items():
        per_mod[m] = per_mod.get(m, 0) + 1
    print("  按模态:", per_mod)

    # 台账入库完再把本体长出来：单文档长不出跨文档取证，另四份样例的
    # 疾病/科室/检查按文档写明的关系进三元组（mcp-server/ontology_grow.py）
    import ontology_extend  # noqa: PLC0415
    import ontology_grow  # noqa: PLC0415

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    grown = ontology_grow.grow(con)
    con.commit()
    # v0.9 到此为止：37 条冻结基线，不再往这个版本里加东西。
    # 之后长出来的关系属于 v1.0——表格与指南里写着、但 pathway 摘要没有的边
    # （首选/次选检查、以某检查确诊、首选药物），见 mcp-server/ontology_extend.py。
    # 写进 v1.0 而不是 v0.9：否则 v0.9 快照会被改写，「37」这个基线就不可复现了。
    ext = ontology_extend.grow(con, "v1.0")
    con.commit()
    con.close()
    print("  跨文档本体:", grown["docs"], "份文档 /", grown["triples"], "条新三元组",
          grown["skipped"] or "")
    print("  表格与指南:", ext["triples"], "条新三元组（重复跳过", ext["duplicate"], "条）")
    if ext["unresolved"]:
        print("  写不出实体（等对齐）:", len(ext["unresolved"]), "处")

    # 生长完必须把版本台账推进到「当前活跃集」：只写 triples 表不写 version 行，
    # health 的 ontology_version / diff_versions / 回滚基线就还是 seed 的 37 条
    # （评审 #31 P1-1）。容器 entrypoint 只跑 ingest_all、不跑 publish.py，
    # 所以这一步放在这里，保证任何入口跑完都满足
    #   version.triple_count == count(active triples)。
    os.environ["MEDPAL_DB"] = str(DB)
    import publish  # noqa: PLC0415

    pub = publish.publish("v1.0", "ingest_all：样本入库 + 跨文档本体生长")
    if not pub.get("ok"):
        print(f"版本发布失败：{pub.get('reason')}（{pub.get('hint', '')}）", file=sys.stderr)
        return 1
    print(
        "  版本台账:", pub["version"],
        "| 三元组:", pub["snapshot"]["triple_count"],
        "| hash:", pub["snapshot"]["manifest_hash"],
        "| 一致:", pub.get("ledger_consistent"),
    )

    odd = [(n, m) for n, m in mapping.items() if (n.endswith((".csv", ".xlsx")) and m != "table")]
    if odd:
        print("  ⚠ 表格类但模态不是 table:", odd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
