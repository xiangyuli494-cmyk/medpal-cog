"""防止人工取证脚本把宿主机或示例回答记成平台验收。"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manual", ROOT / "tools/w2_manual_evidence.py")
manual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manual)
INIT = json.dumps({"result": {"serverInfo": {"name": "medpal-cog"}}})


def test_host_success_cannot_mask_container_failure(monkeypatch):
    replies = iter([(1, "container unavailable"), (0, INIT)])
    monkeypatch.setattr(manual, "run", lambda *a, **k: next(replies))
    result = manual.check_m2("http://test/mcp")
    assert not result["ok"]
    assert INIT in result["host_diagnostic"]
    assert result["raw"] == "container unavailable"


@pytest.mark.parametrize("code,response,ok", [
    (0, INIT, True), (0, "data: " + INIT + "\n\n", True),
    (1, INIT, False), (0, '{"error":"medpal-cog"}', False),
    (0, '{"result":null}', False),
])
def test_only_successful_initialize_counts(monkeypatch, code, response, ok):
    monkeypatch.setattr(manual, "run", lambda *a, **k: (code, response))
    assert manual.check_m2("http://test/mcp")["ok"] == ok


@pytest.mark.parametrize("answer,reviewed,ok", [
    ("科室：消化内科\n检查项：胃镜\n完整率：1.00", True, True),
    ("科室：消化内科\n检查项：胃镜\n完整率：1.00", False, False),
    ("科室：\n检查项：\n完整率：1.50", True, False),
    ("检查项：胃镜\n科室：消化内科\n完整率：0.75", True, False),
    ("科室：消化内科\n检查项：胃镜\n完整率：nan", True, False),
])
def test_m3_requires_real_content_and_manual_review(monkeypatch, tmp_path, answer, reviewed, ok):
    def run(cmd):
        assert cmd[cmd.index("-o") + 1] == os.devnull
        return 0, "200"
    monkeypatch.setattr(manual, "run", run)
    p = tmp_path / "answer.txt"
    p.write_text(answer, encoding="utf-8")
    assert manual.check_m3("http://test", p, reviewed)["ok"] == ok


def test_output_outside_repo_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(manual, "check_m1", lambda *a: {"id": "M-1", "ok": True,
                        "title": "containers", "detail": "test fixture", "raw": ""})
    monkeypatch.setattr(manual, "check_m2", lambda *a: {"id": "M-2", "ok": True,
                        "title": "initialize", "detail": "test fixture", "raw": ""})
    assert manual.main(["--skip-m3", "--out-dir", str(tmp_path)]) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1
