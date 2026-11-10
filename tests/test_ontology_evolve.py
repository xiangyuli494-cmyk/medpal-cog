"""本体进化链：v0.9 → v1.0 必须真的留下版本轨迹，而不是把数字改大。

这套测试盯的是 issue #22 / #23 的闸门条件：
- version 表要有多行、is_current 指向 v1.0（验收 A-09 数快照文件，这里数库里的行）
- 快照文件的行数要等于该版本的三元组数（否则「回放」是假的）
- diff_versions(v0.9, v1.0) 必须能看到新增（评委要的是可回放，不是一句「变好了」）
- 二次运行幂等：同一份语料跑两遍不能越跑越多、manifest 不能变
- 别名跟版本走：「缺铁性贫血」在 v0.9 语料里不存在，v1.0 才认得出 —— 这就是「决策会变」的机械原因
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import ontology_evolve  # noqa: E402
import store  # noqa: E402


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setenv("MEDPAL_DB", str(tmp_path / "evo.db"))
    c = store.connect(tmp_path / "evo.db")
    yield c
    c.close()


def test_evolve_leaves_version_trace(conn):
    stats = ontology_evolve.evolve(conn)
    rows = conn.execute("SELECT version, is_current FROM version ORDER BY rowid").fetchall()
    versions = [r["version"] for r in rows]
    assert versions[0] == "v0.9"
    assert versions[-1] == "v1.0"
    assert [r["version"] for r in rows if r["is_current"]] == ["v1.0"]
    assert store.current_version(conn)["version"] == "v1.0"
    assert stats["triples_total"] > stats["diff"]["added"]


def test_snapshot_matches_triple_count(conn):
    ontology_evolve.evolve(conn)
    info = store.snapshot(conn, "v1.0", note="resnapshot")  # 幂等重写，行数不变
    lines = Path(info["snapshot_path"]).read_text(encoding="utf-8").splitlines()
    count = conn.execute("SELECT COUNT(*) FROM triple WHERE status='active'").fetchone()[0]
    assert len(lines) == count == info["triple_count"]


def test_diff_v09_v10_is_replayable(conn):
    stats = ontology_evolve.evolve(conn)
    diff = store.diff_versions(conn, "v0.9", "v1.0")
    assert diff["counts"]["added"] >= 10
    assert diff["counts"]["removed"] == 0
    assert diff["counts"] == stats["diff"]


def test_second_run_is_idempotent(conn):
    first = ontology_evolve.evolve(conn)
    second = ontology_evolve.evolve(conn)
    assert second["manifest_hash"] == first["manifest_hash"]
    assert second["triples_total"] == first["triples_total"]
    n = conn.execute("SELECT COUNT(*) FROM triple WHERE status='active'").fetchone()[0]
    assert n == first["triples_total"]


def test_alias_follows_version(conn):
    """v0.9 认不出「缺铁性贫血」，v1.0 认得出 —— 同一个问题两种答案的机械原因。"""
    ontology_evolve.ontology_grow.grow(conn)  # 只长基线
    before = store.resolve_entity(conn, "缺铁性贫血")
    ontology_evolve.evolve(conn)
    after = store.resolve_entity(conn, "缺铁性贫血")
    assert before is None
    assert after == "D50.9"  # resolve_entity 返回实体编码，不是整行


def test_batch2_docs_are_shaped():
    for rel in ontology_evolve.ontology_grow.BATCH2:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "ICD-10" in text and "就诊科室" in text
        assert text.count("## ") >= 4
