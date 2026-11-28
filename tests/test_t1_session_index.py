"""会话摘要必须能定位实际执行日志，不把调用文本当成功证据。"""

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["normal", "alarm", "conflict"])
def test_summary_resolves_actual_execution_events_and_trace_result(mode):
    session = json.loads((ROOT / f"agent/sessions/real-w3-{mode}.json").read_text("utf-8"))
    folder = ROOT / "agent/deliverables/w3/nexent"
    log = folder / f"{mode}-actions.json"
    actions = json.loads(log.read_text("utf-8"))
    canonical = json.dumps(actions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert digest == session["actions_canonical_sha256"]
    assert session["conversation_id"] is None
    assert "not returned" in session["conversation_id_status"]
    names = set()
    for call in session["mcp_execution_index"]:
        code = actions[call["code_event_index"]]
        result = actions[call["result_event_index"]]
        assert code["type"] == "parse" and result["type"] == "execution_logs"
        parsed = ast.parse(code["content"])
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == call["tool"] and n.lineno == call["code_line"]
                   for n in ast.walk(parsed))
        assert call["call_source"] in code["content"]
        assert result["content"].strip()
        names.add(call["tool"])
    assert {"health", "std_align", "kg_query", "get_asset_card", "trace_write"} <= names
    result_log = actions[session["trace_write_result_event_index"]]["content"]
    returned = json.JSONDecoder().raw_decode(result_log[result_log.find("{"):])[0]
    assert returned == session["tool_calls"][0]["result"]
    view = json.loads((folder / f"{mode}-trace.json").read_text("utf-8"))
    conversion = json.loads((folder / f"{mode}-conversion.json").read_text("utf-8"))
    for field in ["schema", "sources", "unresolved", "trace_completeness"]:
        assert conversion["added_fields"][field]["value"] == view[field]
        assert conversion["added_fields"][field]["source"]
    assert view["trace_completeness"] == returned["trace_completeness"]
    assert view["unresolved"] == returned["unresolved"]
