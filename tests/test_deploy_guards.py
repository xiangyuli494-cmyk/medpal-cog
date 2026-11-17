"""容器启动的守卫：0 份样本不该返回 0，灌库不该把已发布的版本退回 v0.9。

对应评审 #36 的三条：
- T2 第 3 条：`ingest_all` 在「0 份样本」时照样 exit 0，entrypoint 的 `|| exit 1` 永不触发；
- T1 [P1]：已有库再灌一次，`grow()` 把 current_version 从 v1.0 写回 v0.9、旧快照被覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
os.environ.setdefault("MEDPAL_DB", str(TMP / "guard.db"))

sys.path.insert(0, str(ROOT / "mcp-server"))
sys.path.insert(0, str(ROOT / "tools"))
import ontology_grow  # noqa: E402
import seed  # noqa: E402
import store  # noqa: E402


def test_ingest_all_returns_nonzero_when_no_samples(monkeypatch) -> None:
    import ingest_all  # noqa: PLC0415

    empty = TMP / "empty-samples"
    empty.mkdir(exist_ok=True)
    monkeypatch.setattr(ingest_all, "SAMPLES", empty)
    monkeypatch.setattr(ingest_all, "DB", TMP / "guard-ingest.db")
    rc = ingest_all.main()
    assert rc != 0, "0 份样本必须返回非 0，否则 entrypoint 的 || exit 1 形同虚设"


def test_grow_does_not_downgrade_published_version() -> None:
    db = TMP / "guard-version.db"
    if db.exists():
        db.unlink()
    store.DB_PATH = db
    store.DATA_DIR = TMP
    store.REPORT_DIR = TMP / "reports"
    seed.main(reset=True)

    conn = store.connect()
    try:
        store.snapshot(conn, "v1.0", "已发布版本（模拟 onto_commit）")
        conn.commit()
        before = [
            dict(r)
            for r in conn.execute(
                "SELECT version,triple_count,manifest_hash,is_current FROM version ORDER BY version"
            )
        ]
        ontology_grow.grow(conn, docs=["data/samples/text/pathway_01.md"])
        after = [
            dict(r)
            for r in conn.execute(
                "SELECT version,triple_count,manifest_hash,is_current FROM version ORDER BY version"
            )
        ]
        cur = store.current_version(conn)
    finally:
        conn.close()

    assert cur["version"] == "v1.0", f"灌库后版本指针退回 {cur['version']}，运行期发布的版本被抹了"
    assert before == after, "旧快照被改写"
