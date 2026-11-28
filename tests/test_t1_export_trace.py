import importlib.util
import json
import re
from pathlib import Path

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t1_export", ROOT / "tools/t1_export_trace.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_report_contains_trace_without_file_picker_or_server():
    trace = json.loads((ROOT / "tests/fixtures/trace_v1_example.json").read_text("utf-8"))
    trace["question"] = '</script><img src=x onerror="alert(1)">'
    report = module.export_html(trace, "<unverified>")
    embedded = re.search(r'id="embedded-trace">(.*?)</script>', report, re.S)[1]
    assert json.loads(embedded) == trace
    assert "</script>" not in embedded
    assert "&lt;unverified&gt;" in report
    assert "render(JSON.parse(" in report


def test_broken_trace_remains_broken_after_export():
    trace = json.loads((ROOT / "tests/fixtures/trace_v1_broken.json").read_text("utf-8"))
    assert trace["unresolved"]
    report = module.export_html(trace, "测试夹具")
    embedded = re.search(r'id="embedded-trace">(.*?)</script>', report, re.S)[1]
    assert json.loads(embedded)["unresolved"] == trace["unresolved"]


def test_incomplete_trace_cannot_be_published_as_report():
    with pytest.raises(ValidationError):
        module.export_html({"trace_id": "missing-required-fields"})
