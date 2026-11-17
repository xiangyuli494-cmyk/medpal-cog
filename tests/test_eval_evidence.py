"""证据召回与科室回显的回归：四道锁，防止「假满分母」复活。

背景（W3 评审 P1）：score_one 之前从 gold 里读 gold_evidence，而 gold_evidence 在
dataset 每行的顶层，于是取到的恒为空集、evidence 永远返回 1.0——空除以空。
修好传参后 v1 的真实证据召回是 0.476（21 条有声明锚点），不是 1.000。

这里锁住三件事：
1) 传了声明锚点、输出证据为空 → 0 分，不许给满分；
2) 负例与无锚点题不进分母；
3) v1 全量重算不会退回 1.0（退回就是又变回空满分母了）。

另外锁科室回显的判据：问句在征求科室选择、句中没有症状/疾病时，不给科室结论。
只按「实体类型只剩 Department」判会漏掉「长期吃止痛药，要看消化内科吗」这一类。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["MEDPAL_DB"] = str(TMP / "eval_evidence.db")
if (TMP / "eval_evidence.db").exists():
    (TMP / "eval_evidence.db").unlink()

sys.path.insert(0, str(ROOT / "mcp-server"))
import store  # noqa: E402

store.DATA_DIR = TMP
store.DB_PATH = TMP / "eval_evidence.db"
store.REPORT_DIR = TMP / "reports"

import seed  # noqa: E402

seed.main(reset=True)

sys.path.insert(0, str(ROOT / "eval"))
import run_eval  # noqa: E402

V1 = ROOT / "eval" / "dataset" / "v1.jsonl"
POSITIVE_GOLD = {"dept": "消化内科", "exams": ["胃镜"], "conflicts": []}


def _answer(question: str) -> dict:
    conn = store.connect()
    try:
        return run_eval.answer(conn, question)
    finally:
        conn.close()


def test_declared_anchor_with_empty_evidence_scores_zero() -> None:
    got = {
        "dept": "消化内科",
        "exams": ["胃镜"],
        "conflicts": [],
        "evidence": [],
        "trace_completeness": 1.0,
    }
    sc = run_eval.score_one(POSITIVE_GOLD, got, ["AST-2026-000137#s5.p1.c1"])
    assert sc["evidence"] == 0.0, "输出证据为空时证据召回必须是 0，不能是 1.0"


def test_declared_anchor_half_hit() -> None:
    got = {
        "dept": "消化内科",
        "exams": ["胃镜"],
        "conflicts": [],
        "evidence": ["AST-2026-000137#s5.p1.c1"],
        "trace_completeness": 1.0,
    }
    sc = run_eval.score_one(
        POSITIVE_GOLD,
        got,
        ["AST-2026-000137#s5.p1.c1", "AST-2026-000137#t1.r4"],
    )
    assert sc["evidence"] == 0.5


def test_negative_example_not_in_denominator() -> None:
    gold = {"dept": "", "exams": [], "conflicts": [], "out_of_scope": True}
    got = {"dept": "", "exams": [], "conflicts": [], "evidence": [], "trace_completeness": 1.0}
    sc = run_eval.score_one(gold, got, None)
    assert sc["evidence"] is None, "负例没有声明锚点，不能进证据召回分母（那是白送 1.0）"


def test_v1_real_recall_does_not_regress_to_one() -> None:
    rows = [json.loads(line) for line in V1.read_text(encoding="utf-8").splitlines() if line]
    conn = store.connect()
    try:
        scores = []
        for row in rows:
            got = run_eval.answer(conn, row["question"])
            sc = run_eval.score_one(row["gold"], got, row.get("gold_evidence"))
            if sc["evidence"] is not None:
                scores.append(sc["evidence"])
    finally:
        conn.close()
    assert len(scores) == 21, f"v1 里有声明锚点的题应为 21 条，实际 {len(scores)}"
    avg = sum(scores) / len(scores)
    # 第 3 条要的是「没有变回 1.0」，不是钉死某一位小数：本体补锚点后这个数应当上升。
    assert avg < 0.9, f"证据召回 {avg:.3f} 接近 1.0，很像又退回空满分母了"


def test_dept_echo_blocked_when_only_drug_or_exam_mentioned() -> None:
    for q in ("长期吃止痛药，需要看消化内科吗", "我做过胃镜了，还要看消化内科吗"):
        got = _answer(q)
        assert got["dept"] == "", f"「{q}」应拒答，实际答了 {got['dept']}"
        assert got["evidence"] == [], f"「{q}」拒答后不该再挂证据清单"


def test_symptom_question_still_picks_dept() -> None:
    got = _answer("上腹隐痛、反酸烧心，挂哪个科")
    assert got["dept"] == "消化内科", "有症状的问句不能被回显护栏误杀"
