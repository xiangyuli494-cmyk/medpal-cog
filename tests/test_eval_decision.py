"""决策层回归：两条容易写反的规则。

1) 报警症状（呕血/黑便/消瘦/吞咽困难）优先内镜——即使病史已明确、即使没在索要检查清单，
   也不能把胃镜当成「已做过」丢掉。「消化性溃疡 + 黑便」得出零检查项就是这条规则写反了。
2) 冲突只在问题里真的提到那个药时上报。否则任何消化性溃疡问题都会被挂上「布洛芬」，
   把一条用药提醒冒充成患者正在吃的药。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["MEDPAL_DB"] = str(TMP / "eval_decision.db")
if (TMP / "eval_decision.db").exists():
    (TMP / "eval_decision.db").unlink()

sys.path.insert(0, str(ROOT / "mcp-server"))
import store  # noqa: E402

store.DATA_DIR = TMP
store.DB_PATH = TMP / "eval_decision.db"
store.REPORT_DIR = TMP / "reports"

import seed  # noqa: E402

seed.main(reset=True)

sys.path.insert(0, str(ROOT / "eval"))
import run_eval  # noqa: E402


def _answer(question: str) -> dict:
    conn = store.connect()
    try:
        return run_eval.answer(conn, question)
    finally:
        conn.close()


def test_alarm_keeps_gastroscopy_even_when_disease_known():
    got = _answer("既往消化性溃疡，最近出现黑便")
    assert got["dept"] == "消化内科"
    assert "胃镜" in got["exams"], got["exams"]


def test_known_disease_without_alarm_skips_gastroscopy():
    # 病史明确、也没在索要检查清单：内镜视为已做，只补病因学检查
    got = _answer("确诊消化性溃疡需要查幽门螺杆菌吗")
    assert "胃镜" not in got["exams"], got["exams"]
    assert "幽门螺杆菌呼气试验" in got["exams"], got["exams"]


def test_conflict_only_when_drug_is_mentioned():
    quiet = _answer("上腹隐痛三个月，夜间加重")
    assert quiet["conflicts"] == [], quiet["conflicts"]

    spoken = _answer("胃溃疡病史，长期服用止痛药会不会伤胃")
    assert "布洛芬" in spoken["conflicts"], spoken["conflicts"]
