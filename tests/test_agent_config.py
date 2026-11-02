"""主智能体配置的自洽性校验。

配置类文件最容易腐烂：工具改名了白名单没改、Skill 目录改名了提示词还指着旧名、
输出契约写在三处各不相同。这里只做"能机器判的"部分，平台上的真实表现不在此列。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agent"

# 与 tools/acceptance.py 的 TOOL_CONTRACT 同源：10 个 MCP 工具是写进赛题方案的对外契约
TOOLS = [
    "ingest_asset",
    "get_asset_card",
    "kg_query",
    "onto_propose",
    "onto_commit",
    "std_align",
    "trace_write",
    "skill_export",
    "kb_search",
    "health",
]


def load_config() -> dict:
    return json.loads((AGENT / "config.json").read_text(encoding="utf-8"))


def test_tool_whitelist_matches_contract():
    assert sorted(load_config()["tools"]["mcp"]) == sorted(TOOLS)


def test_prompt_mentions_every_tool():
    prompt = (AGENT / "prompt.md").read_text(encoding="utf-8")
    missing = [t for t in TOOLS if t not in prompt]
    assert not missing, f"提示词没提这些工具：{missing}"


def test_skills_exist():
    for rel in load_config()["skills"]:
        assert (ROOT / rel / "SKILL.md").is_file(), f"{rel} 缺 SKILL.md"


def test_prompt_has_three_line_tail():
    prompt = (AGENT / "prompt.md").read_text(encoding="utf-8")
    for line in ("科室：", "检查项：", "完整率："):
        assert prompt.count(line) >= 1


def test_sessions_match_output_contract():
    cfg = load_config()["output_contract"]
    patterns = [re.compile(p) for p in cfg["patterns"]]
    files = sorted((AGENT / "sessions").glob("*.json"))
    assert len(files) >= 3, "至少三份样例：常态 / 报警 / 冲突"
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        tail = data["expected_tail"]
        assert len(tail) == cfg["tail_lines"], f"{f.name} 尾行数不对"
        for line, pat in zip(tail, patterns):
            assert pat.match(line), f"{f.name} 尾行不符合契约：{line}"
        if data["conflict_line"]:
            assert re.match(cfg["conflict_line"], data["conflict_line"])
        assert all(e.startswith("AST-2026-") for e in data["evidence"])


def test_real_sessions_have_provenance():
    """agent/sessions/real-*.json 必须是 Nexent 实跑记录，不是手写的"看起来像实跑"。

    判据三条：source 写明 Nexent 实跑与时间；tool_calls 非空且每条都带 ok；
    证据锚点全部挂在真实资产上。不校验平台端的原始 SSE（那在提交者本地）。
    """
    files = sorted((AGENT / "sessions").glob("real-*.json"))
    assert files, "至少一份 Nexent 实跑记录：real-w1-01.json"
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "Nexent 实跑" in data["source"], f"{f.name} 没写实跑来源"
        assert re.search(r"20\d{2}-\d{2}-\d{2}", data["source"]), f"{f.name} 缺实跑日期"
        calls = data.get("tool_calls") or []
        assert calls, f"{f.name} 没有任何 MCP 工具调用"
        assert all("ok" in c for c in calls), f"{f.name} 有工具调用没记结果"
        assert any(c["ok"] for c in calls), f"{f.name} 全部工具调用都失败，不能当成功证据"


def test_guardrails_present():
    prompt = (AGENT / "prompt.md").read_text(encoding="utf-8")
    for g in load_config()["guardrails"]:
        assert g in prompt, f"提示词缺护栏：{g}"
