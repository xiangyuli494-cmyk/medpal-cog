"""ontology_extend 的抽取规则：复合症状词要拆开、不能整条丢掉。

防的失败方式：`test_guide_01` 原文「患者出现上腹隐痛、反酸烧心症状，建议及时就诊」
里，`反酸烧心` 中间没有顿号。只按 `、`/「和」切词时它会是一个整体词，`_typed_id`
查不到 alias 就整条丢弃——于是「反酸烧心该挂消化内科」这条**分诊知识**进不了图，
而 eval 里 H001 / Q017 / Q020 / Q023 问的正是「烧心反酸要做什么检查 / 挂哪个科」。

拆词也不许乱猜：切不动的字一律放弃整串，不能把半截词硬塞进本体。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import ontology_extend  # noqa: E402
import store  # noqa: E402


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))
    c = store.connect()
    for surface, code, etype in [
        ("上腹隐痛", "SYM-EPI", "Symptom"),
        ("反酸", "SYM-HEART", "Symptom"),
        ("烧心", "SYM-HEART", "Symptom"),
        ("消化内科", "DEP-GI", "Department"),
    ]:
        c.execute(
            "INSERT OR REPLACE INTO alias (surface,code,scheme,entity_type,confidence) "
            "VALUES (?,?,?,?,?)",
            (surface, code, "local", etype, 0.9),
        )
    # 正名从三元组里来（schema §2.2：head_label 存中文正名，不存表面词）。
    # 刻意用 has_symptom 而不是 belongs_to_dept 落地——要测的那条边不能事先存在，
    # 否则被测的代码只会判重，测不出「以前整条丢弃」这个缺陷。
    store.add_triple(
        c,
        {
            "head": {"id": "K21", "type": "Disease", "label": "胃食管反流病"},
            "rel": "has_symptom",
            "tail": {"id": "SYM-HEART", "type": "Symptom", "label": "烧心"},
            "confidence": 0.85,
            "provenance": {"asset_id": "AST-T0", "anchor_id": "AST-T0#p1"},
            "standard": {},
        },
        version="v0.9",
    )
    c.commit()
    yield c
    c.close()


def _guide(conn, anchor_id, text):
    conn.execute(
        "INSERT OR REPLACE INTO asset (asset_id,title,modality,anchors_json) VALUES (?,?,?,?)",
        (
            "AST-GUIDE",
            "test_guide_01 01",
            "pdf_text",
            json.dumps(
                [{"anchor_id": anchor_id, "kind": "page", "text": text}], ensure_ascii=False
            ),
        ),
    )
    conn.commit()


def _anchors(conn, items):
    """按真实文档的锚点集写卡：科室名在标题锚点里，症状清单在前言里。"""
    conn.execute(
        "INSERT OR REPLACE INTO asset (asset_id,title,modality,anchors_json) VALUES (?,?,?,?)",
        (
            "AST-GUIDE",
            "test_guide_01 01",
            "pdf_text",
            json.dumps(items, ensure_ascii=False),
        ),
    )
    conn.commit()


def test_compound_symptom_splits_into_known_nodes(conn):
    """「反酸烧心」要拆成 反酸 + 烧心，两个都由同一个节点承接，不能整条丢。"""
    assert ontology_extend._symptom_ids(conn, "反酸烧心") == ["SYM-HEART"]
    assert ontology_extend._symptom_ids(conn, "上腹隐痛") == ["SYM-EPI"]


def test_unknown_symptom_returns_empty_not_guess(conn):
    """切不动就返回空，不猜——猜出来的节点会污染本体。"""
    assert ontology_extend._symptom_ids(conn, "反酸肚子疼乱码") == []
    assert ontology_extend._symptom_ids(conn, "不存在的症状") == []


def test_guide_registry_symptom_dropped_before_is_now_added(conn):
    """回归：就诊指南里「反酸烧心」的归口边以前被静默丢弃，现在必须进库。

    锚点按真实文档摆：科室名在标题锚点（「第一章 消化内科就诊指南」），
    症状清单在前言锚点。同一个卡里两段话分工，这是 pdf_parser 的真实产出形状。
    """
    _anchors(
        conn,
        [
            {
                "anchor_id": "AST-GUIDE#p1.pre",
                "kind": "page",
                "text": "这是就诊指南前言：患者出现上腹隐痛、反酸烧心症状，建议及时就诊。",
            },
            {
                "anchor_id": "AST-GUIDE#p1.h1",
                "kind": "heading",
                "text": "第一章 消化内科就诊指南",
            },
        ],
    )
    stats = {"triples": 0, "duplicate": 0, "unresolved": [], "added": []}
    ontology_extend.grow_from_guides(conn, "v1.0", stats)

    rows = conn.execute(
        "SELECT head_id, head_label FROM triple WHERE rel='belongs_to_dept' "
        "AND tail_id='DEP-GI' AND asset_id='AST-GUIDE'"
    ).fetchall()
    got = {r["head_id"]: r["head_label"] for r in rows}
    assert "SYM-HEART" in got, got
    assert got["SYM-HEART"] == "烧心", "head_label 要存中文正名，不是表面词「反酸」"
    assert "SYM-EPI" in got, "「上腹隐痛」那条也要在"
    assert not [u for u in stats["unresolved"] if "反酸" in u], stats["unresolved"]