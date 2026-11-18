import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t1_paths", ROOT / "tools/t1_check_paths.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_empty_case_set_cannot_receive_a_passing_verdict():
    with pytest.raises(ValueError):
        module.audit(Path("unused.db"), [])


def test_foreign_anchors_cannot_fake_cross_document_paths():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(module.store.SCHEMA)
    anchors = [{"anchor_id": f"REAL#p{i}"} for i in range(2)]
    conn.execute(
        "INSERT INTO asset(asset_id,anchors_json,title,modality) VALUES ('REAL',?,'test','text')",
        (json.dumps(anchors),),
    )
    steps = []
    for i, (head, tail) in enumerate([("A", "B"), ("B", "C")]):
        triple = {
            "head": {"id": head, "type": "Disease", "label": head},
            "rel": "requires_exam",
            "tail": {"id": tail, "type": "Exam", "label": tail},
            "provenance": {"asset_id": f"CLAIMED-{i}", "anchor_id": f"REAL#p{i}"},
        }
        tid = module.store.add_triple(conn, triple)
        steps.append({"head_id": head, "tail_id": tail, "rel": "requires_exam",
                      "triple_id": tid, "provenance": triple["provenance"]})
    assert not module.qualifies(conn, {"nodes": ["A", "B", "C"], "steps": steps},
                                {"seeds": ["A"], "hops": 2, "terminal": "C"})
    conn.close()


@pytest.mark.parametrize("fault", [None, "same_document", "missing_anchor", "disconnected"])
def test_paths_require_real_continuous_cross_document_evidence(fault):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(module.store.SCHEMA)
    steps = []
    for i, (head, tail) in enumerate([( "A", "B"), ("B", "C")]):
        asset = "AST-2026-A" if fault == "same_document" else f"AST-2026-{i}"
        anchor = asset + "#p1"
        conn.execute(
            "INSERT OR REPLACE INTO asset(asset_id,anchors_json,title,modality) "
            "VALUES (?,?,'test','text')",
            (asset, json.dumps([] if fault == "missing_anchor" else [{"anchor_id": anchor}])),
        )
        triple = {
            "head": {"id": head, "type": "Disease", "label": head},
            "rel": "requires_exam",
            "tail": {"id": tail, "type": "Exam", "label": tail},
            "provenance": {"asset_id": asset, "anchor_id": anchor},
        }
        tid = module.store.add_triple(conn, triple)
        steps.append({"head_id": head, "tail_id": tail, "rel": "requires_exam",
                      "triple_id": tid, "provenance": triple["provenance"]})
    nodes = ["A", "B", "C"] if fault != "disconnected" else ["A", "X", "C"]
    assert module.qualifies(conn, {"nodes": nodes, "steps": steps},
                            {"seeds": ["A"], "hops": 2, "terminal": "C"}) == (fault is None)
    conn.close()
