"""两次启动的持久化探针（CI 用，docker cp 进容器执行，不进镜像）。

--write  造一条运行期上传资产 + 发一个 v1.0 当前版本，基线写 /tmp/persist-baseline.json
--verify 重启后核对：上传资产还在、版本指针仍是 v1.0、快照集合未变（评审 #36 [P1]）
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

DB = os.environ.get("MEDPAL_DB") or "/app/mcp-server/data/medpal.db"
BASE = Path(os.environ.get("MEDPAL_PROBE_BASE") or "/tmp/persist-baseline.json")
PROBE_ID = "AST-2026-runtime01"
# 容器里 DB=/app/mcp-server/data/medpal.db，上两级是 store.py 所在目录；本机自测用 MEDPAL_SERVER_DIR
sys.path.insert(0, os.environ.get("MEDPAL_SERVER_DIR") or str(Path(DB).resolve().parent.parent))
import store  # noqa: E402

SNAPS = "SELECT version,triple_count,manifest_hash,is_current FROM version ORDER BY version"


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _current(con) -> str:
    row = con.execute("SELECT version FROM version WHERE is_current=1").fetchone()
    return row["version"] if row else ""


def write() -> int:
    con = _db()
    if _current(con) != "v1.0":
        store.snapshot(con, "v1.0", "persist_probe: 模拟运行期发布的版本")
        con.commit()
    store.upsert_asset(
        con,
        {
            "asset_id": PROBE_ID,
            "title": "运行期上传的资产（持久化探针）",
            "modality": "text",
            "source": {"type": "runtime_upload"},
            "sensitivity": "public",
            "kb_status": "ready",
            "ingested_by": "ci",
        },
    )
    base = {
        "assets": con.execute("SELECT COUNT(*) c FROM asset").fetchone()["c"],
        "current": _current(con),
        "snapshots": [dict(r) for r in con.execute(SNAPS)],
        "probe_id": PROBE_ID,
    }
    con.close()
    BASE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] 写入完成：asset={base['assets']} current={base['current']}")
    return 0


def verify() -> int:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    con = _db()
    assets = con.execute("SELECT COUNT(*) c FROM asset").fetchone()["c"]
    current = _current(con)
    snaps = [dict(r) for r in con.execute(SNAPS)]
    rows = con.execute("SELECT COUNT(*) c FROM asset WHERE asset_id=?", (base["probe_id"],))
    probe_rows = rows.fetchone()["c"]
    con.close()

    problems = []
    if probe_rows != 1:
        problems.append("运行期上传的资产被抹掉了（重启重灌）")
    if current != base["current"]:
        problems.append(f"版本指针被改：{base['current']} -> {current}")
    if assets != base["assets"]:
        problems.append(f"asset 行数变了：{base['assets']} -> {assets}")
    if snaps != base["snapshots"]:
        problems.append("快照集合被改写（旧快照不保）")

    for p in problems:
        print(f"[probe] FAIL {p}")
    if problems:
        return 1
    print(
        f"[probe] OK 两次启动后：asset={assets}（含 1 条运行期上传）"
        f" current={current} 快照 {len(snaps)} 个未变"
    )
    return 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        raise SystemExit(write())
    if "--verify" in sys.argv:
        raise SystemExit(verify())
    print("用法：persist_probe.py --write | --verify")
    raise SystemExit(2)
