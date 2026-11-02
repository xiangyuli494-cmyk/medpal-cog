"""防止「旧六人计划」以任何形式回到现行文档里。

2026-11-02：六人版角色卡 docs/W1-角色任务卡.md 删除，README 曾把它当现行文档链着，
导致队友按旧排期领活。这里把规则钉死：仓内只能存在一份现行排期。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACTIVE_PLAN = ROOT / "docs" / "冲刺计划-1130.md"
ACTIVE_CARD = ROOT / "docs" / "任务卡-三人版.md"
ARCHIVED_PLAN = ROOT / "docs" / "赛题3-方案-v1.2.md"
REMOVED_CARD = ROOT / "docs" / "W1-角色任务卡.md"


def test_six_person_card_stays_deleted() -> None:
    assert not REMOVED_CARD.exists(), "六人版角色卡不应回到仓库；历史见 git / 旧仓 medpal"


def test_readme_does_not_link_removed_card() -> None:
    for rel in ("README.md", "docs/README.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "W1-角色任务卡.md" not in text, f"{rel} 仍在引用已删除的六人版角色卡"


def test_active_plan_is_three_person_and_dated() -> None:
    plan = ACTIVE_PLAN.read_text(encoding="utf-8")
    assert "三人" in plan
    assert "11-30" in plan or "11/30" in plan
    card = ACTIVE_CARD.read_text(encoding="utf-8")
    for handle in ("T1", "T2", "T3"):
        assert handle in card, f"任务卡缺少 {handle}"


def test_archived_plan_is_marked_superseded() -> None:
    text = ARCHIVED_PLAN.read_text(encoding="utf-8")
    head = text[:2000]
    assert "已被取代" in head and "冲刺计划-1130.md" in head
