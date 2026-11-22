"""回滚：把本体退回已发布版本（经 onto_commit(to=...) 这个对外入口）。

防的失败方式：
1. 回滚不生效——目标版本之后新增的三元组还留着，kg_query 拿回不该有的知识。
2. 回滚把目标版本里已有的三元组也标成删了，知识凭空少一片。
3. 没有快照文件也照回滚，静默退化成「什么都不做」。
4. 回滚不推进版本号，事后分不清库处在哪个状态。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import server  # noqa: E402
import store  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """一套独立的库和快照目录，不碰仓库里的 medpal.db。

    关键：`store.connect()` 无参时读模块级 `DB_PATH`，所以必须连同
    `server._conn()` 一起指过去；`DATA_DIR` 也要换，否则快照写进仓库。
    """
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setattr(server, "store", store)
    # server._conn() 走 MEDPAL_DB，不设就会读仓库里的真实库
    monkeypatch.setenv("MEDPAL_DB", str(db))
    store.connect().close()  # connect 里建表，拿到一个空库
    return db, data_dir


def _add(conn, label: str, version: str = "v0.9"):
    return store.add_triple(
        conn,
        {
            "head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
            "rel": "treated_by",
            "tail": {"id": "DRUG-" + label, "type": "Drug", "label": label},
            "confidence": 0.8,
            "provenance": {"asset_id": "AST-1", "anchor_id": "AST-1#p1"},
            "standard": {},
        },
        version=version,
    )


def test_rollback_removes_triples_added_after_target(fresh_db):
    """v1.0 之后新增的知识，回滚到 v1.0 后必须消失。"""
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v1.0", "基准")
    _add(conn, "乙药", "v1.1")
    store.snapshot(conn, "v1.1", "加了一条")
    conn.close()

    res = server.onto_commit(diff_id="", to="v1.0", version="v1.2")
    assert res["ok"], res
    assert res["removed"] == 1, res

    conn = store.connect()
    rows = conn.execute("SELECT tail_label FROM triple WHERE status='active'")
    labels = {r["tail_label"] for r in rows}
    conn.close()
    assert "甲药" in labels
    assert "乙药" not in labels


def test_rollback_keeps_triples_that_were_in_target(fresh_db):
    """目标版本里就有的知识，回滚不能把它删掉。"""
    conn = store.connect()
    _add(conn, "甲药")
    _add(conn, "丙药")
    store.snapshot(conn, "v1.0", "两条")
    store.snapshot(conn, "v1.1", "没加东西")
    conn.close()

    res = server.onto_commit(diff_id="", to="v1.0", version="v1.2")
    assert res["ok"], res
    assert res["removed"] == 0, res

    conn = store.connect()
    n = conn.execute("SELECT count(*) c FROM triple WHERE status='active'").fetchone()["c"]
    conn.close()
    assert n == 2


def test_rollback_revives_removed_triple(fresh_db):
    """被删掉的知识回到目标版本时应当复活，而不是永久消失。"""
    conn = store.connect()
    tid = _add(conn, "戊药")
    store.snapshot(conn, "v1.0", "有戊药")
    conn.execute(
        "UPDATE triple SET status='removed', version_removed='v1.1' WHERE triple_id=?", (tid,)
    )
    store.snapshot(conn, "v1.1", "删了戊药")
    conn.close()

    res = server.onto_commit(diff_id="", to="v1.0", version="v1.2")
    assert res["ok"], res
    assert res["revived"] == 1, res

    conn = store.connect()
    row = conn.execute("SELECT status FROM triple WHERE triple_id=?", (tid,)).fetchone()
    conn.close()
    assert row["status"] == "active"


def test_rollback_rejects_unregistered_target(fresh_db):
    """目标版本没在 version 表里登记过时必须报错，不能拿一份来历不明的快照回滚。

    防的错：旧实现只看 `ontology_<target>.jsonl` 存不存在。手工留下的文件、
    或从别的库拷来的快照都能骗过它，回滚出的「目标版本」在这个库里从未发布过。
    """
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v1.0", "基准")
    conn.close()

    res = server.onto_commit(diff_id="", to="v9.9", version="v1.2")
    assert res["ok"] is False
    assert res["reason"] == "version_not_registered", res


def test_rollback_rejects_missing_snapshot(fresh_db):
    """版本表登记过、但快照文件被删了：报 snapshot_not_found，不静默当成无事可做。"""
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v1.0", "基准")
    conn.close()
    (fresh_db[1] / "ontology_v1.0.jsonl").unlink()

    res = server.onto_commit(diff_id="", to="v1.0", version="v1.2")
    assert res["ok"] is False
    assert res["reason"] == "snapshot_not_found", res


def test_rollback_rejects_empty_target(fresh_db):
    """直接调回滚入口且没写目标时，给明确原因，不猜。

    对外入口是 onto_commit(to=...)：`to` 为空就退化成普通提交，
    所以这条测的是内层 onto_rollback 的防御。
    """
    res = server.onto_rollback(target="", version="v1.2")
    assert res["ok"] is False
    assert res["reason"] == "target_required"


def test_rollback_callable_without_diff_id(fresh_db):
    """回滚是 `onto_commit(to=...)`，调用方不该被迫编一个 diff 号。

    `diff_id` 曾经是必填位置参数，于是 `onto_commit(to="v1.0")` 在签名层就抛
    TypeError —— 测试里都写成 `onto_commit(diff_id="", to=...)` 才跑得过去，
    把「回滚入口根本没接通」这件事整套盖住了。演练时真实调用才露出来。
    """
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v1.0", "基准")
    conn.close()

    res = server.onto_commit(to="v1.0", version="v1.1")  # 不传 diff_id
    assert res["ok"], res


def test_commit_without_diff_id_returns_reason_not_crash(fresh_db):
    """普通提交漏传 diff_id 时回 reason，不让 None 走进 SQL。"""
    store.connect().close()
    res = server.onto_commit()
    assert res["ok"] is False
    assert res["reason"] == "diff_id_required"


def test_rollback_bumps_version(fresh_db):
    """回滚是一次发布：版本号前进，当前指针指到新版本。"""
    conn = store.connect()
    _add(conn, "甲药")
    store.snapshot(conn, "v1.0", "基准")
    _add(conn, "乙药", "v1.1")
    store.snapshot(conn, "v1.1", "加了一条")
    conn.close()

    res = server.onto_commit(diff_id="", to="v1.0", version="v1.2")
    assert res["version"] == "v1.2"
    assert res["previous"] == "v1.1"

    conn = store.connect()
    cur = conn.execute("SELECT version FROM version WHERE is_current=1").fetchone()
    rows = conn.execute("SELECT version FROM version ORDER BY created_at")
    versions = [r["version"] for r in rows]
    conn.close()
    assert cur["version"] == "v1.2"
    assert versions == ["v1.0", "v1.1", "v1.2"]


def test_rollback_restores_revised_confidence_and_provenance(fresh_db):
    """`revise` 抬过的置信度与换过的出处，回滚到旧版本时必须一并还原。

    防的错（评审 #31 P1-2）：旧实现只按 triple_id 改 status，`revise` 是原地 UPDATE，
    没有任何留痕。结果回滚后条数对、快照 hash 却和目标版本对不上——名义回滚、数据没回。
    快照里本来就存了 confidence / asset_id / anchor_id，按目标快照写回即可。
    """
    conn = store.connect()
    tid = store.add_triple(
        conn,
        {
            "head": {"id": "K27", "type": "Disease", "label": "消化性溃疡"},
            "rel": "treated_by",
            "tail": {"id": "DRUG-A", "type": "Drug", "label": "甲药"},
            "confidence": 0.8,
            "provenance": {"asset_id": "AST-1", "anchor_id": "AST-1#p1"},
            "standard": {},
        },
        version="v1.0",
    )
    store.snapshot(conn, "v1.0", "基准")
    # 模拟 onto_commit 的 revise：原地抬置信度、换更直接的出处
    conn.execute(
        "UPDATE triple SET confidence=0.95, asset_id='AST-2', anchor_id='AST-2#p9' "
        "WHERE triple_id=?",
        (tid,),
    )
    store.snapshot(conn, "v1.1", "revise")
    conn.close()

    res = server.onto_commit(to="v1.0", version="v1.2")
    assert res["ok"], res
    assert res["restored"] == 1, res
    assert res["revived"] == 0 and res["removed"] == 0, res

    conn = store.connect()
    row = conn.execute(
        "SELECT confidence, asset_id, anchor_id FROM triple WHERE triple_id=?", (tid,)
    ).fetchone()
    target_hash = conn.execute(
        "SELECT manifest_hash FROM version WHERE version='v1.0'"
    ).fetchone()["manifest_hash"]
    rollback_hash = conn.execute(
        "SELECT manifest_hash FROM version WHERE version='v1.2'"
    ).fetchone()["manifest_hash"]
    conn.close()
    assert row["confidence"] == pytest.approx(0.8)
    assert row["asset_id"] == "AST-1"
    assert row["anchor_id"] == "AST-1#p1"
    # 回滚后的快照必须与目标版本逐条一致——hash 相同才算真的回去了
    assert rollback_hash == target_hash