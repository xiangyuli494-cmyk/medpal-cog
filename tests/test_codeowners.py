"""CODEOWNERS 不能留占位符，且 owner 必须是我们真实加过的人。

占位符（@T2_HANDLE / @T3_HANDLE）会让 GitHub 把整条规则当成无效 owner：
看起来「有人管」，实际评审请求不会发给任何人，而 require_code_owner_reviews
一旦打开就会直接卡住合并。用一条测试把它锁在 PR 阶段。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEOWNERS = ROOT / "CODEOWNERS"
KNOWN = {"@xiangyuli494-cmyk", "@zincumyu", "@Dewqian"}


def _rule_lines() -> list[str]:
    return [
        line
        for line in CODEOWNERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_no_placeholder_handles():
    text = CODEOWNERS.read_text(encoding="utf-8")
    for bad in ("@T2_HANDLE", "@T3_HANDLE", "T2_HANDLE", "T3_HANDLE"):
        assert bad not in text, f"CODEOWNERS 里还有占位符 {bad}"


def test_owner_rules_point_to_known_accounts():
    owners = {
        m.group(0)
        for line in _rule_lines()
        for m in re.finditer(r"@[A-Za-z0-9][A-Za-z0-9-]*", line)
    }
    assert owners, "CODEOWNERS 没有任何 owner 规则"
    # 加人时同步改这里，避免「改了 CODEOWNERS 忘了加 Collaborator」。
    assert owners <= KNOWN, owners


def test_every_rule_has_an_owner():
    for line in _rule_lines():
        assert "@" in line, f"这条规则没有 owner：{line}"
