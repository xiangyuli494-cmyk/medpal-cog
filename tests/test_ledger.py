"""台账页 web/ledger.html 必须与资产卡一致，且不泄漏本机绝对路径。

原因：台账页是 W2-T3-3 的交付物——双击可开、不连后端。它是生成物：
手改过、或资产卡更新后忘了重跑，页面就开始骗人；而卡里若写着
`E:\\...\\data\\samples\\...` 这种绝对路径又原样渲染进页面，等于把某台
机器的工作目录提交进了仓库（PR #27 评审里点过的同一个坑）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_ledger  # noqa: E402


def test_ledger_is_up_to_date():
    cards = gen_ledger.load_cards()
    doc = gen_ledger.build_page(cards)
    current = gen_ledger.OUT_PATH.read_text(encoding="utf-8")
    assert current == doc, "web/ledger.html 不是最新，请跑 python tools/gen_ledger.py"


def test_ledger_covers_every_card():
    cards = gen_ledger.load_cards()
    doc = gen_ledger.build_page(cards)
    assert len(cards) >= gen_ledger.MIN_CARDS
    for card in cards:
        assert card["asset_id"] in doc
    assert doc.count("<tr data-mod=") == len(cards)


def test_ledger_has_no_absolute_path():
    cards = gen_ledger.load_cards()
    doc = gen_ledger.build_page(cards)
    assert gen_ledger.ABS_PATH_RE.search(doc) is None, "台账页里出现了盘符路径"
