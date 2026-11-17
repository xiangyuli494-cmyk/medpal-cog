"""三跳验收的回归：声明 hops 必须真走，且不许拿「同文档三段关系」冒充跨文档三跳。

背景（T1 的 [P2]）：`answer(conn, question)` 固定 `max_hops=2`，dataset 里 `hops: 3`
根本没被读，也没有路径长度 / 跨文档断言——所以「W3 三跳已验收」这句话当时没有依据。

这里锁三件事：
1) 按声明的 3 跳调用，最长路径真的到 3 跳，跳数达成得分 1.0；
2) 退回默认 2 跳，同一题跳数达成得 0.0（旧行为会被这条抓出来）；
3) 跨文档这一项当前是 0：10 条三跳题的最长路径全部落在同一份文档里，
   如实报 0，不吹。本体补了跨文档三元组之后这条会红，那时该改的是断言，不是数据。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["MEDPAL_DB"] = str(TMP / "eval_multihop.db")
if (TMP / "eval_multihop.db").exists():
    (TMP / "eval_multihop.db").unlink()

sys.path.insert(0, str(ROOT / "mcp-server"))
import store  # noqa: E402

store.DATA_DIR = TMP
store.DB_PATH = TMP / "eval_multihop.db"
store.REPORT_DIR = TMP / "reports"

import seed  # noqa: E402

seed.main(reset=True)

sys.path.insert(0, str(ROOT / "eval"))
import run_eval  # noqa: E402

V1 = ROOT / "eval" / "dataset" / "v1.jsonl"
ROWS = [json.loads(line) for line in V1.read_text(encoding="utf-8").splitlines() if line.strip()]


def _row(qid: str) -> dict:
    return next(r for r in ROWS if r["id"] == qid)


def _answer(question: str, hops: int = 2) -> dict:
    conn = store.connect()
    try:
        return run_eval.answer(conn, question, max_hops=hops)
    finally:
        conn.close()


def test_declared_three_hops_are_really_walked() -> None:
    row = _row("Q001")
    assert row["hops"] == 3
    got = _answer(row["question"], hops=3)
    assert got["path_hops"] >= 3, f"声明 3 跳，最长路径只有 {got['path_hops']} 跳"
    sc = run_eval.score_one(row["gold"], got, row.get("gold_evidence"), 3)
    assert sc["path"] == 1.0


def test_default_two_hops_scores_zero_against_declared_three() -> None:
    row = _row("Q001")
    got = _answer(row["question"], hops=2)
    assert got["path_hops"] == 2
    sc = run_eval.score_one(row["gold"], got, row.get("gold_evidence"), 3)
    assert sc["path"] == 0.0, "固定 2 跳对声明 3 跳的题必须判不合格，否则等于没测"


def test_negative_row_not_in_path_denominator() -> None:
    row = _row("Q028")
    got = _answer(row["question"], hops=int(row.get("hops") or 2))
    sc = run_eval.score_one(row["gold"], got, row.get("gold_evidence"), row.get("hops"))
    assert sc["path"] is None and sc["cross_doc"] is None


def test_cross_doc_three_hop_is_still_zero_today() -> None:
    rows = [r for r in ROWS if int(r.get("hops") or 0) >= 3]
    assert rows, "v1 里应该有声明 3 跳的题"
    scores = []
    for row in rows:
        got = _answer(row["question"], hops=3)
        sc = run_eval.score_one(row["gold"], got, row.get("gold_evidence"), 3)
        scores.append(sc["cross_doc"])
    # 当前本体：三跳链全在同一份文档（AST-2026-000137）里，所以这一项是 0。
    # 这是如实记账，不是「三跳已验收」。
    assert all(s == 0.0 for s in scores), "跨文档三跳出现了，本体已经补上，改这条断言并更新交接单"
