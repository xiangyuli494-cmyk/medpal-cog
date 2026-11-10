import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples"
CARDS = ROOT / "data" / "asset-cards"
DB = ROOT / "mcp-server" / "data" / "medpal.db"
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
        # 结尾补一个换行：POSIX 文本文件约定，也免得 git 每次提示 "No newline at end of file"
        (CARDS / f"{card['asset_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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
    import ontology_grow  # noqa: PLC0415

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    grown = ontology_grow.grow(con)
    con.commit()
    con.close()
    print("  跨文档本体:", grown["docs"], "份文档 /", grown["triples"], "条新三元组",
          grown["skipped"] or "")

    # 再走一遍「工具链进化」：第二批文档 propose → commit 出版本，
    # 让库里的本体不是一次性写死，而是留有 v0.9 → v1.0 的版本轨迹（W2 进化预演）
    import ontology_evolve  # noqa: PLC0415

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    evo = ontology_evolve.evolve(con)
    con.commit()
    con.close()
    print("  本体进化:", evo["base_version"], "→", evo["new_version"],
          "| 候选", evo["proposed"], "条 / 提交", evo["committed"],
          "| 版本内", evo["triples_total"], "条 | manifest", evo["manifest_hash"])
    odd = [(n, m) for n, m in mapping.items() if (n.endswith((".csv", ".xlsx")) and m != "table")]
    if odd:
        print("  ⚠ 表格类但模态不是 table:", odd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
