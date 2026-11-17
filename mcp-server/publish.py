"""把当前活跃三元组发布成一个本体版本：version 表 +1、写快照、可被 `diff_versions` 回放。

为什么需要它：`store.snapshot()` 只写快照文件并覆盖 `version` 表的那一行，不推进版本；
而 `onto_commit` 是按「待审 diff」提交的。流水线（seed → ingest → 生长）跑完后，
要把这批关系正式定格成 v1.0，就得有一次「把当前全部活跃三元组当成一次提交」的动作。

实现方式：造一份覆盖全部活跃三元组的 diff（已有的会被 `add_triple` 判重挡掉），
再调 `server.onto_commit` —— **不走写库旁路**，版本推进与快照仍然只由那一个入口负责。

用法：python mcp-server/publish.py [--version v1.0] [--note 说明]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))


def _current_rows(conn) -> list:
    return conn.execute(
        "SELECT triple_id, head_id, head_type, head_label, rel, tail_id, tail_type, "
        "tail_label, confidence, asset_id, anchor_id, standard_json "
        "FROM triple WHERE status='active' ORDER BY triple_id"
    ).fetchall()


def publish(version: str = "v1.0", note: str = "") -> dict:
    """把当前活跃三元组提交成 `version`。已经是当前版本时只重写快照（幂等）。"""
    import server  # noqa: PLC0415  必须在 sys.path 设好之后导入
    import store  # noqa: PLC0415

    conn = store.connect()
    try:
        cur = store.current_version(conn)
        rows = _current_rows(conn)
        if not rows:
            return {"ok": False, "reason": "no_triples", "hint": "库里没有活跃三元组"}
        if cur and cur["version"] == version:
            snap = store.snapshot(conn, version, note or f"{version} 重写快照")
            return {"ok": True, "version": version, "already": True, "snapshot": snap}

        payload = [
            {
                "head": {"id": r["head_id"], "type": r["head_type"], "label": r["head_label"]},
                "rel": r["rel"],
                "tail": {"id": r["tail_id"], "type": r["tail_type"], "label": r["tail_label"]},
                "confidence": r["confidence"],
                "provenance": {"asset_id": r["asset_id"], "anchor_id": r["anchor_id"]},
                "standard": json.loads(r["standard_json"] or "{}"),
            }
            for r in rows
        ]
        diff_id = "DF-PUBLISH-" + uuid.uuid4().hex[:8]
        conn.execute(
            "INSERT INTO pending_diff (diff_id,status,payload,created_at) VALUES (?,?,?,?)",
            (diff_id, "pending", json.dumps(payload, ensure_ascii=False), store.now()),
        )
        conn.commit()
    finally:
        conn.close()

    res = server.onto_commit(
        diff_id=diff_id, version=version, note=note or "publish active triples"
    )
    res["diff_id"] = diff_id
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把当前活跃三元组发布成新版本")
    ap.add_argument("--version", default="v1.0")
    ap.add_argument("--note", default="W2 本体：表格与指南抽取")
    args = ap.parse_args(argv)

    res = publish(args.version, args.note)
    if not res.get("ok"):
        print("发布失败:", res, file=sys.stderr)
        return 1

    import store  # noqa: PLC0415

    conn = store.connect()
    try:
        cur = store.current_version(conn)
        print(
            "版本:", res["version"],
            "| 新增:", res.get("added"),
            "| 三元组:", cur["triple_count"],
            "| hash:", cur["manifest_hash"],
        )
        print("快照:", res["snapshot"]["snapshot_path"])
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())