"""T1 业务题的只读路径预检；图路径通过不等于 Nexent 会话已验收。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))
import store  # noqa: E402


def qualifies(conn, path: dict, case: dict) -> bool:
    nodes, steps = path.get("nodes", []), path.get("steps", [])
    if len(steps) != case["hops"] or len(nodes) != len(steps) + 1:
        return False
    if nodes[0] not in case["seeds"] or nodes[-1] != case["terminal"]:
        return False
    assets = []
    for i, step in enumerate(steps):
        if {nodes[i], nodes[i + 1]} != {step["head_id"], step["tail_id"]}:
            return False
        row = conn.execute(
            "SELECT * FROM triple WHERE triple_id=? AND status='active'",
            (step["triple_id"],),
        ).fetchone()
        if not row or (row["head_id"], row["tail_id"], row["rel"]) != (
            step["head_id"], step["tail_id"], step["rel"]
        ):
            return False
        prov = step.get("provenance", {})
        asset, anchor = prov.get("asset_id"), prov.get("anchor_id")
        if not asset or not anchor or (asset, anchor) != (row["asset_id"], row["anchor_id"]):
            return False
        # 锚点必须属于声明的资产，不能用其他文档的真实锚点冒充跨文档证据。
        if not isinstance(anchor, str) or not anchor.startswith(str(asset) + "#"):
            return False
        if not store._evidence_exists(conn, anchor):
            return False
        assets.append(asset)
    return all(a != b for a, b in zip(assets, assets[1:]))


def audit(db: Path, cases: list[dict]) -> dict:
    if (
        sum(c.get("hops") == 2 for c in cases) < 3
        or sum(c.get("hops") == 3 for c in cases) < 1
        or len({c["id"] for c in cases}) != len(cases)
    ):
        raise ValueError("需至少三道两跳、一道三跳题，且题号不得重复")
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        current = store.current_version(conn)
        results = []
        for case in cases:
            result = store.kg_query(conn, case["seeds"], max_hops=case["hops"], limit=10000)
            paths = [p for p in result.get("paths", []) if qualifies(conn, p, case)]
            results.append({"case": case, "graph_ready": bool(paths), "paths": paths[:1]})
        return {
            "source": "read-only graph audit; not Nexent session evidence",
            "version": current["version"] if current else None,
            "ready": all(r["graph_ready"] for r in results),
            "results": results,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "mcp-server/data/medpal.db")
    parser.add_argument("--cases", type=Path, default=ROOT / "agent/validation/w3-cases.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.db, json.loads(args.cases.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in result["results"]:
        print(row["case"]["id"], "READY" if row["graph_ready"] else "BLOCKED")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
