"""活文档里不许再出现旧六人代号（T4/T5/T6、xy-Z5）。

背景：队伍从 6 人缩到 3 人后，`docs/judge-guide.md`、`docs/mcp-contract.md`、
`docs/handoff/` 一度还写着 T4/T6，评委按文档找人会对不上。历史记录类文档
（`docs/赛题3-方案-v1.2.md`、`docs/charter.md`、`docs/env.md`、`docs/adr/ADR-002*`）
继续保留旧代号，那是史料，不在本测试范围内。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 现行文档：写给人照着做的，代号必须是 T1 / T2 / T3
LIVE_DOCS = [
    "README.md",
    "docs/judge-guide.md",
    "docs/mcp-contract.md",
    "docs/trace-schema.md",
    "docs/ontology-schema.md",
    "docs/T3-可视化输入契约.md",
    "docs/开工检查单.md",
]

OLD_CODES = re.compile(r"\bT[456]\b")


def live_paths() -> list[Path]:
    paths = [ROOT / p for p in LIVE_DOCS]
    paths += sorted((ROOT / "docs" / "handoff").glob("*.md"))
    return [p for p in paths if p.exists()]


def test_live_docs_have_no_old_role_codes() -> None:
    bad: list[str] = []
    for path in live_paths():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if OLD_CODES.search(line):
                bad.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()[:80]}")
    assert not bad, "活文档里还有旧代号 T4/T5/T6：\n" + "\n".join(bad)


def test_left_team_handle_only_in_history() -> None:
    """xy-Z5 已离队；除历史快照外不该再出现。"""
    allowed = {"docs/赛题3-方案-v1.2.md", "docs/冲刺计划-1130.md"}
    bad: list[str] = []
    for path in sorted(ROOT.glob("docs/**/*.md")) + [ROOT / "README.md"]:
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed or not path.exists():
            continue
        if "xy-Z5" in path.read_text(encoding="utf-8"):
            bad.append(rel)
    assert not bad, "xy-Z5 已离队，请从这些文件删掉：" + ", ".join(bad)