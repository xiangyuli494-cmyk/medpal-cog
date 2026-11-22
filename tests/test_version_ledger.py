"""版本台账不变量：`version.triple_count` 必须等于活跃三元组数。

评审 #31 P1-1 的现场：`seed --reset` + `ingest_all` 之后库里 44 条活跃边，
但 `version` 表只有一行 `v0.9 / 37`——`health().ontology_version`、`diff_versions`、
回滚基线全部拿到 37。容器 entrypoint 只跑 ingest_all，起来就是 37 / 44 两套数。

修法是把「发布当前活跃集」放进生长流程（`tools/ingest_all.py` 末尾），任何入口
跑完都过 `store.ledger_consistent()`；这组测试守住这个不变量和「不许把版本指针退回去」。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))
sys.path.insert(0, str(ROOT / "tools"))

import publish  # noqa: E402
import store  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))
    store.connect().close()
    return db, data_dir


def _add(conn, label, version="v0.9", conf=0.8):
    return store.add_triple(
        conn,
        {
            "head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
            "rel": "treated_by",
            "tail": {"id": "DRUG-" + label, "type": "Drug", "label": label},
            "confidence": conf,
            "provenance": {"asset_id": "AST-1", "anchor_id": "AST-1#p1"},
            "standard": {},
        },
        version=version,
    )


def test_publish_keeps_version_ledger_consistent(fresh_db):
    """发布后当前版本的 triple_count 必须等于活跃三元组数。"""
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v0.9", "种子")
    _add(conn, "乙药", "v1.0")
    _add(conn, "丙药", "v1.0")
    conn.close()

    res = publish.publish("v1.0", "测试")
    assert res["ok"], res
    assert res["ledger_consistent"] is True, res

    conn = store.connect()
    cur = store.current_version(conn)
    assert cur["version"] == "v1.0"
    assert cur["triple_count"] == store.active_count(conn) == 3
    conn.close()


def test_publish_is_idempotent_when_version_is_current(fresh_db):
    """同一版本重复发布只重写快照，不新增行，不破坏一致性。"""
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v0.9", "种子")
    _add(conn, "乙药", "v1.0")
    conn.close()

    first = publish.publish("v1.0", "第一次")
    second = publish.publish("v1.0", "第二次")
    assert first["ok"] and second["ok"], (first, second)
    assert second.get("already") is True, second
    assert second["ledger_consistent"] is True, second

    conn = store.connect()
    versions = [r["version"] for r in conn.execute("SELECT version FROM version ORDER BY version")]
    assert versions == ["v0.9", "v1.0"], versions
    assert store.current_version(conn)["triple_count"] == 2
    conn.close()


def test_publish_refuses_to_rewind_current_version(fresh_db):
    """当前已是 v1.1 时再 publish("v1.0") 必须拒绝，不能把版本指针和旧快照改回去。

    防的错：重灌库（容器 `MEDPAL_INGEST=rebuild`）或重跑流水线时，若 v1.0 是历史版本，
    `INSERT OR REPLACE version` 会把它重新标成 current，历史被静默改写。
    要发新内容就给新版本号，交给人决定。
    """
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v0.9", "种子")
    _add(conn, "乙药", "v1.0")
    conn.close()
    publish.publish("v1.0", "第一次")

    conn = store.connect()
    _add(conn, "丙药", "v1.1")
    store.snapshot(conn, "v1.1", "后续提交")
    conn.close()

    res = publish.publish("v1.0", "重灌库")
    assert res["ok"] is False, res
    assert res["reason"] == "version_not_current", res

    conn = store.connect()
    assert store.current_version(conn)["version"] == "v1.1"
    conn.close()


def test_ingest_all_publishes_and_leaves_ledger_consistent(fresh_db, tmp_path, monkeypatch):
    """`ingest_all` 跑完必须自己发布版本，而不是把一致性留给调用方补 publish。

    容器 entrypoint 只跑 ingest_all；这里用一份最小样本走真实入口，
    断言跑完 `current_version.triple_count == count(active triples)`。
    """
    import ingest_all  # noqa: PLC0415

    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "pathway_k27.md").write_text(
        "# 消化性溃疡临床路径\n\n## 诊断\n确诊依赖胃镜检查。\n", encoding="utf-8"
    )
    cards = tmp_path / "cards"
    cards.mkdir()
    db = tmp_path / "ingest.db"
    # ingest_all 假定库已经由 seed 建好表，这里先建 schema
    store.connect(db).close()
    monkeypatch.setattr(ingest_all, "SAMPLES", samples)
    monkeypatch.setattr(ingest_all, "CARDS", cards)
    monkeypatch.setattr(ingest_all, "DB", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))

    assert ingest_all.main() == 0

    conn = store.connect(db)
    cur = store.current_version(conn)
    assert cur is not None, "ingest_all 跑完没有版本行"
    assert cur["triple_count"] == store.active_count(conn), (
        f"版本台账 {cur['triple_count']} ≠ 活跃 {store.active_count(conn)}"
    )
    assert store.ledger_consistent(conn)
    conn.close()


def test_snapshot_round_trips_confidence_and_provenance(fresh_db):
    """快照文件必须带 confidence / asset_id / anchor_id，回滚才还原得回来。

    防的错：只写 triple_id 和两端 id 的话，`onto_rollback` 没有数据可回填，
    又退化成「只改 status」。
    """
    conn = store.connect()
    _add(conn, "甲药", conf=0.83)
    snap = store.snapshot(conn, "v0.9", "种子")
    conn.close()

    lines = [
        json.loads(line)
        for line in Path(snap["snapshot_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, "快照是空的"
    row = lines[0]
    for key in ("triple_id", "confidence", "asset_id", "anchor_id"):
        assert key in row, row
    assert row["confidence"] == pytest.approx(0.83)
    assert row["anchor_id"] == "AST-1#p1"