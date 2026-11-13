"""onto_propose 的三类规则：别名命中 / ICD-10 缺对齐 / 同义关系冲突。

这个文件只测「候选怎么出来」，不测写库（写库归 test_onto_commit.py）。
每条测试都对着一种会真实发生的错：

1. 别名命中的表面词（「胃溃疡」）没归一到 canonical id（K27）→ 候选头尾指向两个节点，
   入库后同一件事在图上出现两遍。
2. 疾病节点没有 `aligned_to_standard` 边，`std_align` 只能靠别名表兜，规格里要求的
   「ICD-10 对齐 ≥30 条」永远涨不上去。
3. 同一 head 同一关系下挂着互为别名的两个 tail（「胃溃疡」和「消化性溃疡」都被当成
   检查的尾），检索时同一件事出现两条边。
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
    """独立库 + 独立快照目录，不碰仓库里的 medpal.db。"""
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))
    conn = store.connect()
    conn.close()
    return db, data_dir


def _seed_entities(conn):
    """最小实体底座：两个疾病、一个检查、四个别名（含一对同义词）。"""
    for surface, code, scheme, etype, conf in [
        ("消化性溃疡", "K27", "ICD-10", "Disease", 0.98),
        ("胃溃疡", "K27", "ICD-10", "Disease", 0.9),
        ("胃炎", "K29", "ICD-10", "Disease", 0.95),
        ("胃镜", "EX-GASTRO", "local", "Exam", 0.92),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO alias (surface,code,scheme,entity_type,confidence) "
            "VALUES (?,?,?,?,?)",
            (surface, code, scheme, etype, conf),
        )
    conn.commit()


def _add_triple(conn, head, rel, tail, anchor="AST-T1#p1", conf=0.8):
    return store.add_triple(
        conn,
        {
            "head": head,
            "rel": rel,
            "tail": tail,
            "confidence": conf,
            "provenance": {"asset_id": "AST-T1", "anchor_id": anchor},
            "standard": {},
        },
        version="v0.9",
    )


def _make_asset(conn, asset_id, anchors):
    conn.execute(
        "INSERT OR REPLACE INTO asset (asset_id,title,modality,anchors_json) VALUES (?,?,?,?)",
        (asset_id, "测试资产", "text", __import__("json").dumps(anchors, ensure_ascii=False)),
    )
    conn.commit()


def _disease(code, label):
    return {"id": code, "type": "Disease", "label": label}


def test_alias_hit_canonicalizes_head_and_tail(fresh_db):
    """别名命中：表面词（胃溃疡）必须落到 canonical id（K27），不能另起节点。

    防的错：`expand()` 抓到「胃溃疡」，`resolve_entity` 返回 K27，但候选里的
    `label` 还是「胃溃疡」——入库后同一疾病在 label 索引里有两个名字。
    """
    conn = store.connect()
    _seed_entities(conn)
    _make_asset(
        conn,
        "AST-T1",
        [
            {
                "anchor_id": "AST-T1#p1",
                "kind": "sentence",
                "text": "胃溃疡患者需要做胃镜检查以明确病变的部位与分期",
            }
        ],
    )
    conn.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MEDPAL_DB", str(fresh_db[0]))
        res = server.onto_propose(["AST-T1"])

    assert res["ok"], res
    head = [c for c in res["candidates"] if c["rel"] == "requires_exam"]
    assert head, res["candidates"]
    c = head[0]
    # 别名表里「胃溃疡」→ K27，候选头必须是 K27 而不是自造的 DIS-xxx
    assert c["head"]["id"] == "K27", c
    # 别名命中要把原表面词留在 via_alias 里，便于审计「这个节点是怎么归过来的」
    assert c["head"].get("via_alias") == "胃溃疡", c


def test_icd_missing_alignment_proposes_aligned_edge(fresh_db):
    """ICD-10 缺对齐：疾病节点没有 aligned_to_standard 边时，补一条对齐候选。

    防的错：v0.9 里 7 条对齐边只覆盖有编码的疾病，`std_align` 遇到新疾病只能返回
    unmapped，卡在待对齐队列里永远长不上去。
    """
    conn = store.connect()
    _seed_entities(conn)
    # K27 有编码但库里还没有对齐边
    _add_triple(
        conn,
        _disease("K27", "消化性溃疡"),
        "requires_exam",
        {"id": "EX-GASTRO", "type": "Exam", "label": "胃镜"},
    )
    _make_asset(
        conn,
        "AST-T1",
        [
            {
                "anchor_id": "AST-T1#p1",
                "kind": "sentence",
                "text": "胃溃疡患者需要做胃镜检查以明确病变的部位与分期",
            }
        ],
    )
    conn.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MEDPAL_DB", str(fresh_db[0]))
        res = server.onto_propose(["AST-T1"])

    aligned = [c for c in res["candidates"] if c["rel"] == "aligned_to_standard"]
    assert aligned, [c["rel"] for c in res["candidates"]]
    got = aligned[0]
    assert got["head"]["id"] == "K27"
    assert got["tail"]["id"] == "ICD10-K27"
    assert got["rule"] == "icd_missing_alignment"


def test_synonym_conflict_proposes_deprecate(fresh_db):
    """同义关系冲突：同一 head 同一关系下挂着互为别名的两个 tail，提废弃。

    防的错：`store.add_triple` 按 `(head_id, rel, tail_id)` 判重，节点相同才拦得住。
    如果两条边用了不同的 tail id（老数据里「内窥镜检查」和「胃镜」各建了一个节点），
    判重拦不住，同一个事实在图上挂两条边。
    """
    conn = store.connect()
    _seed_entities(conn)
    # 「内窥镜检查」是「胃镜」的另一种写法，但历史上被建成了 EX-OLD 这个独立节点
    conn.execute(
        "INSERT OR IGNORE INTO alias (surface,code,scheme,entity_type,confidence) "
        "VALUES ('内窥镜检查','EX-GASTRO','local','Exam',0.9)"
    )
    thumb = {"id": "EX-OLD", "type": "Exam", "label": "内窥镜检查"}
    _add_triple(conn, _disease("K29", "胃炎"), "requires_exam", thumb, anchor="AST-T0#p9")
    _make_asset(
        conn,
        "AST-T1",
        [
            {
                "anchor_id": "AST-T1#p1",
                "kind": "sentence",
                "text": "慢性胃炎患者需要做胃镜检查以明确病变范围",
            }
        ],
    )
    conn.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MEDPAL_DB", str(fresh_db[0]))
        res = server.onto_propose(["AST-T1"])

    dep = [c for c in res["candidates"] if c["kind"] == "deprecate"]
    assert dep, [(c["kind"], c["head"]["label"], c["tail"]["label"]) for c in res["candidates"]]
    assert dep[0]["conflict"]["dropped"] == "内窥镜检查"
    assert dep[0]["target_triple_id"], dep[0]