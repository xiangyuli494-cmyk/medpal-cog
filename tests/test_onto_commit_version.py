"""onto_commit 的版本推进：version +1、快照落盘、diff 可回放、schema 外关系不入库。

防的失败方式：
1. 提交后 `version` 表还是只有一行——「等于没提交过」，W2 闸门的两条判定都挂在这。
2. 快照文件没写出或内容与库不一致，`diff_versions` 读不到，回放不了。
3. schema 之外的 `rel`（`may_cause` 等）被写进库，图里出现词表外的边。
4. 非法类型（检查 → 检查）被写进库。
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
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))
    store.connect().close()
    return db, data_dir


def _asset(conn, asset_id="AST-T1", anchors=None):
    import json

    anchors = anchors or [
        {"anchor_id": f"{asset_id}#p1", "kind": "sentence", "text": "慢性胃炎患者需要做胃镜检查"}
    ]
    conn.execute(
        "INSERT OR REPLACE INTO asset (asset_id,title,modality,anchors_json) VALUES (?,?,?,?)",
        (asset_id, "测试", "text", json.dumps(anchors, ensure_ascii=False)),
    )
    for surface, code, etype in [("胃炎", "K29", "Disease"), ("胃镜", "EX-GASTRO", "Exam")]:
        conn.execute(
            "INSERT OR REPLACE INTO alias (surface,code,scheme,entity_type,confidence) "
            "VALUES (?,?,?,?,?)",
            (surface, code, "local", etype, 0.9),
        )
    conn.commit()


def _diff(conn, items):
    import json
    import uuid

    diff_id = "DF-TEST-" + uuid.uuid4().hex[:6]
    conn.execute(
        "INSERT INTO pending_diff (diff_id,status,payload,created_at) VALUES (?,?,?,?)",
        (diff_id, "pending", json.dumps(items, ensure_ascii=False), store.now()),
    )
    conn.commit()
    return diff_id


def _cand(kind="new", rel="requires_exam", conf=0.9, anchor="AST-T1#p1"):
    return {
        "kind": kind,
        "head": {"id": "K29", "type": "Disease", "label": "胃炎"},
        "rel": rel,
        "tail": {"id": "EX-GASTRO", "type": "Exam", "label": "胃镜"},
        "confidence": conf,
        "provenance": {"asset_id": "AST-T1", "anchor_id": anchor},
    }


def test_commit_bumps_version_and_writes_snapshot(fresh_db):
    """提交后 version 表要有两行，当前指向新版本，快照文件真的落在 DATA_DIR。"""
    db, data_dir = fresh_db
    conn = store.connect()
    _asset(conn)
    store.snapshot(conn, "v0.9", "种子")
    diff_id = _diff(conn, [_cand()])
    conn.close()

    res = server.onto_commit(diff_id=diff_id, version="v1.0", note="测试")
    assert res["ok"], res
    assert res["added"] == 1, res
    assert res["version"] == "v1.0"
    assert res["previous"] == "v0.9"

    conn = store.connect()
    versions = [r["version"] for r in conn.execute("SELECT version FROM version ORDER BY version")]
    cur = store.current_version(conn)
    conn.close()
    assert versions == ["v0.9", "v1.0"], versions
    assert cur["version"] == "v1.0"
    assert (data_dir / "ontology_v1.0.jsonl").exists()
    # 快照行数必须与库里活跃三元组一致，否则 diff 回放会缺条
    assert len((data_dir / "ontology_v1.0.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_diff_between_versions_is_replayable(fresh_db):
    """`store.diff_versions(v0.9, v1.0)` 要能算出「新增 1 条」，且方向正确。"""
    db, data_dir = fresh_db
    conn = store.connect()
    _asset(conn)
    store.snapshot(conn, "v0.9", "种子")
    diff_id = _diff(conn, [_cand()])
    conn.close()

    server.onto_commit(diff_id=diff_id, version="v1.0", note="测试")

    conn = store.connect()
    d = store.diff_versions(conn, "v0.9", "v1.0")
    conn.close()
    assert d["counts"]["added"] == 1, d["counts"]
    assert d["counts"]["removed"] == 0, d["counts"]
    assert d["added"][0]["signature"][0] == "K29"


def test_commit_skips_rel_not_in_schema(fresh_db):
    """schema 之外的 rel（may_cause）不能入库，但要计数说明跳过了几条。"""
    db, data_dir = fresh_db
    conn = store.connect()
    _asset(conn)
    store.snapshot(conn, "v0.9", "种子")
    diff_id = _diff(conn, [_cand(rel="may_cause", conf=0.72)])
    conn.close()

    res = server.onto_commit(diff_id=diff_id, version="v1.0", note="测试")
    assert res["ok"], res
    assert res["added"] == 0, res
    assert res["skipped_not_in_schema"] == 1, res

    conn = store.connect()
    n = conn.execute("SELECT count(*) c FROM triple WHERE rel='may_cause'").fetchone()["c"]
    conn.close()
    assert n == 0


def test_publish_marks_deprecated_triple_removed(fresh_db):
    """`deprecate` 候选要把目标三元组标成 removed 并记下版本号，不是物理删除。"""
    db, data_dir = fresh_db
    conn = store.connect()
    _asset(conn)
    old = store.add_triple(
        conn,
        {
            "head": {"id": "K29", "type": "Disease", "label": "胃炎"},
            "rel": "requires_exam",
            "tail": {"id": "EX-OLD", "type": "Exam", "label": "内窥镜检查"},
            "confidence": 0.8,
            "provenance": {"asset_id": "AST-T1", "anchor_id": "AST-T1#p1"},
            "standard": {},
        },
        version="v0.9",
    )
    store.snapshot(conn, "v0.9", "种子")
    cand = _cand(kind="deprecate")
    cand["target_triple_id"] = old
    cand["conflict"] = {"kept": "胃镜", "dropped": "内窥镜检查", "triple_id": old}
    diff_id = _diff(conn, [cand])
    conn.close()

    res = server.onto_commit(diff_id=diff_id, version="v1.0", note="测试")
    assert res["ok"], res
    assert res["deprecated"] == 1, res

    conn = store.connect()
    row = conn.execute(
        "SELECT status, version_removed FROM triple WHERE triple_id=?", (old,)
    ).fetchone()
    conn.close()
    assert row["status"] == "removed"
    assert row["version_removed"] == "v1.0"


def test_revise_raises_confidence_not_duplicates(fresh_db):
    """`revise` 只提高置信度、不新增行——否则同一条知识会被反复提交成多条。"""
    db, data_dir = fresh_db
    conn = store.connect()
    _asset(conn)
    tid = store.add_triple(
        conn,
        {
            "head": {"id": "K29", "type": "Disease", "label": "胃炎"},
            "rel": "requires_exam",
            "tail": {"id": "EX-GASTRO", "type": "Exam", "label": "胃镜"},
            "confidence": 0.8,
            "provenance": {"asset_id": "AST-T1", "anchor_id": "AST-T1#p1"},
            "standard": {},
        },
        version="v0.9",
    )
    store.snapshot(conn, "v0.9", "种子")
    cand = _cand(kind="revise", conf=0.95)
    cand["target_triple_id"] = tid
    diff_id = _diff(conn, [cand])
    conn.close()

    res = server.onto_commit(diff_id=diff_id, version="v1.0", note="测试")
    assert res["ok"], res
    assert res["revised"] == 1, res
    assert res["added"] == 0, res

    conn = store.connect()
    rows = conn.execute("SELECT confidence FROM triple WHERE head_id='K29'").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["confidence"] == pytest.approx(0.95)