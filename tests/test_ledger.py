"""台账页 web/ledger.html 必须对得上资产卡，且不泄漏本机绝对路径。

原因：台账页是 W2-T3-3 的交付物——双击可开、不连后端。它是生成物：
手改过、或资产卡更新后忘了重跑，页面就开始骗人；而卡里若写着
`E:\\...\\data\\samples\\...` 这种绝对路径又原样渲染进页面，等于把某台
机器的工作目录提交进了仓库（PR #27 评审里点过的同一个坑）。

与 `acceptance.py --stage w2` 的兼容：闸门会先跑 `seed --reset` + `ingest_all`，
把 data/samples 里未登记进仓库的样本也写成卡（62 → 69）。此时页面是 62 张卡的
基线快照，判等必然失败。所以这里用页面自带的基线清单做判据：卡目录没漂移就
要求逐字节一致，漂移了就退化成「基线全覆盖 + 行数对得上」。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_ledger  # noqa: E402


def test_ledger_matches_cards_or_covers_baseline():
    cards = gen_ledger.load_cards()
    current = gen_ledger.OUT_PATH.read_text(encoding="utf-8")
    problems = gen_ledger.check_page(cards, current)
    assert problems == [], "；".join(problems)


def test_ledger_covers_every_baseline_card():
    current = gen_ledger.OUT_PATH.read_text(encoding="utf-8")
    baseline = gen_ledger.page_baseline(current)
    assert baseline, "台账页缺基线清单，重跑 python tools/gen_ledger.py"
    assert len(baseline) >= gen_ledger.MIN_CARDS
    for asset_id in baseline:
        assert asset_id in current
    assert current.count("<tr data-mod=") == len(baseline)


def test_ledger_has_no_absolute_path():
    cards = gen_ledger.load_cards()
    doc = gen_ledger.build_page(cards)
    assert gen_ledger.ABS_PATH_RE.search(doc) is None, "台账页里出现了盘符路径"


def test_ledger_build_is_repeatable():
    """同输入重复生成必须逐字节一致，否则每次跑都产生假 diff。"""
    cards = gen_ledger.load_cards()
    assert gen_ledger.build_page(cards) == gen_ledger.build_page(cards)
