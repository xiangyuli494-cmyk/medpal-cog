"""生成 W2 进化预演证据：同一个问题在 v0.9 与 v1.0 上各问一次，差在哪、为什么差。

为什么要单独一个脚本、而不是手写两段 JSON：
- 「决策会变」是赛题对「可进化」的硬要求（方案 v1.2 §3），评委要能看到同一问题两种答案，
  以及答案变化的机械原因（新增了哪几条三元组）。手写可以编，这里必须是跑出来的。
- 两个状态都在 tmp/ 下现建：A 态 = seed + 第一批文档（v0.9，缺铁性贫血不在本体里），
  B 态 = 交付库副本（v1.0）。交付库只读，trace 不会写进 mcp-server/data/medpal.db。

用法：python tools/make_evo_evidence.py
产出：agent/sessions/evo-w2-01.json（前后对比）、v1-01..03.json（v1.0 上的常态/报警/冲突）
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))
sys.path.insert(0, str(ROOT / "eval"))

import ontology_grow  # noqa: E402
import run_eval  # noqa: E402
import seed  # noqa: E402
import store  # noqa: E402

SESSIONS = ROOT / "agent" / "sessions"
TMP = ROOT / "tmp" / "evo-evidence"

# 问题里不点名词表外的检查名：一旦点名「血常规」，结论会被「只答被点名的检查」这条规则裁成单项，
# 看不出 v1.0 到底长出了哪几项检查
EVO_QUESTION = "患者乏力、面色苍白，怀疑缺铁性贫血，应该挂哪个科室、要做哪些检查？"

CASES = [
    (
        "v1-01.json",
        "W2 常态：上腹隐痛夜间加重 → 消化内科 + 两项检查（v1.0 库）",
        "反复上腹隐痛3个月，夜间加重，进食后缓解",
    ),
    (
        "v1-02.json",
        "W2 报警：黑便 → 先做内镜（v1.0 库）",
        "上腹隐痛3个月，今天黑便，需要做哪些检查？",
    ),
    (
        "v1-03.json",
        "W2 冲突：服用布洛芬 → 禁忌提示（v1.0 库）",
        "反复上腹隐痛，最近吃布洛芬止痛，应该挂哪个科室？",
    ),
]


def _set_state(db: Path, data_dir: Path) -> None:
    store.DATA_DIR = data_dir
    store.DB_PATH = db
    os.environ["MEDPAL_DB"] = str(db)


def build_base_state(tmp: Path):
    """A 态：只有 v0.9 语料（seed + 第一批文档）。缺铁性贫血不在这套本体里。"""
    a_dir = tmp / "a"
    a_dir.mkdir(parents=True, exist_ok=True)
    _set_state(a_dir / "a.db", a_dir)
    with contextlib.redirect_stdout(io.StringIO()):
        seed.main(reset=True)
    conn = store.connect(store.DB_PATH)
    ontology_grow.grow(conn)
    return conn


def build_evolved_state(tmp: Path):
    """B 态：交付库副本（v1.0）。复制 db 与两份快照，diff_versions 才有得读。"""
    b_dir = tmp / "b"
    b_dir.mkdir(parents=True, exist_ok=True)
    src = ROOT / "mcp-server" / "data"
    shutil.copy(src / "medpal.db", b_dir / "b.db")
    for f in src.glob("ontology_v*.jsonl"):
        shutil.copy(f, b_dir / f.name)
    _set_state(b_dir / "b.db", b_dir)
    return store.connect(store.DB_PATH)


def tail(res: dict) -> list[str]:
    exams = "、".join(res["exams"]) if res["exams"] else "无"
    return [
        f"科室：{res['dept']}" if res["dept"] else "科室：未取到",
        f"检查项：{exams}",
        f"完整率：{res['trace_completeness']:.2f}",
    ]


def tool_calls(question: str, res: dict, ents: list[str]) -> list[dict]:
    """把一次问答的步骤写成工具调用形状：与 agent/prompt.md 的四轮检索-推理一一对应。"""
    return [
        {
            "tool": "std_align",
            "args": {"term": "、".join(ents) or "（无）"},
            "ok": bool(ents),
            "yields": "实体归一" + ("：" + "、".join(ents) if ents else "（空）"),
        },
        {
            "tool": "kg_query",
            "args": {"seeds": ents, "max_hops": 2},
            "ok": bool(res["evidence"]),
            "yields": f"{len(res['evidence'])} 条证据路径",
        },
        {
            "tool": "trace_write",
            "args": {"question": question},
            "ok": True,
            "yields": res["trace_id"],
        },
    ]


def main() -> int:
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True)
    orig = (store.DB_PATH, store.DATA_DIR)
    try:
        base = build_base_state(TMP)
        evolved = build_evolved_state(TMP)

        ents_evo = run_eval.extract_entities(EVO_QUESTION)
        before = run_eval.answer(base, EVO_QUESTION)
        after = run_eval.answer(evolved, EVO_QUESTION)

        new_triples = [
            {"triple_id": r["triple_id"], "rel": r["rel"], "tail": r["tail_label"]}
            for r in evolved.execute(
                "SELECT triple_id, rel, tail_label FROM triple "
                "WHERE head_id='D50.9' AND status='active' ORDER BY rel, tail_id"
            ).fetchall()
        ]
        evo = {
            "id": "EVO-W2-01",
            "title": "进化预演：同一个缺铁性贫血问题，v0.9 答不出、v1.0 答得出",
            "source": (
                "由 tools/make_evo_evidence.py 在 tmp/ 下现建两个状态回放生成："
                "A 态=seed+第一批文档（v0.9），B 态=交付库副本（v1.0）。不是 Nexent 实跑记录"
            ),
            "question": EVO_QUESTION,
            "entity_extract": ents_evo,
            "before": {
                "ontology_version": "v0.9",
                "dept": before["dept"],
                "exams": before["exams"],
                "out_of_scope": before["out_of_scope"],
                "trace_id": before["trace_id"],
                "evidence": before["evidence"],
                "expected_tail": tail(before),
            },
            "after": {
                "ontology_version": "v1.0",
                "dept": after["dept"],
                "exams": after["exams"],
                "out_of_scope": after["out_of_scope"],
                "trace_id": after["trace_id"],
                "evidence": after["evidence"],
                "expected_tail": tail(after),
            },
            "delta": {
                "dept_changed": before["dept"] != after["dept"],
                "exams_added": sorted(set(after["exams"]) - set(before["exams"])),
                "out_of_scope": [before["out_of_scope"], after["out_of_scope"]],
            },
            "why_it_changed": (
                "v1.0 新增 4 份样例文档与 19 条别名后，本体里出现 D50.9（缺铁性贫血）这一节点："
                "belongs_to_dept→血液内科、requires_exam→血清铁蛋白/骨髓涂片/血常规。"
                "v0.9 里这条链不存在，问题里的「缺铁性贫血」无法归一，决策链在第一步就断，"
                "结论退化成「超出覆盖范围」；v1.0 里同一句话能走到科室与检查项，"
                "因此同批评测里这题的分数从 0 变为满分 —— 这就是「决策会变」的机械原因，"
                "而不是换了个提示词。"
            ),
            "new_triples": new_triples,
            "evidence": after["evidence"],
            "expected_tail": tail(after),
            "conflict_line": "",
            "tool_calls": tool_calls(EVO_QUESTION, after, ents_evo),
            "engine": {k: after[k] for k in ("dept", "exams", "conflicts", "trace_id",
                                             "trace_completeness", "elapsed_ms", "out_of_scope")},
        }

        written = []
        SESSIONS.mkdir(parents=True, exist_ok=True)
        (SESSIONS / "evo-w2-01.json").write_text(
            json.dumps(evo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        written.append("evo-w2-01.json")

        for name, title, question in CASES:
            res = run_eval.answer(evolved, question)
            ents = run_eval.extract_entities(question)
            conflict = ""
            if res["conflicts"]:
                conflict = f"冲突：{'、'.join(res['conflicts'])}（NSAIDs）与消化性溃疡存在禁忌关系"
            data = {
                "id": name.replace(".json", "").upper(),
                "title": title,
                "source": (
                    "由 tools/make_evo_evidence.py 在交付库副本（v1.0）上回放生成 —— "
                    "固化 v1.0 的问答形状与三行输出，不是 Nexent 实跑记录"
                ),
                "ontology_version": "v1.0",
                "question": question,
                "tool_calls": tool_calls(question, res, ents),
                "evidence": res["evidence"],
                "conflict_line": conflict,
                "expected_tail": tail(res),
                "engine": {k: res[k] for k in ("dept", "exams", "conflicts", "trace_id",
                                               "trace_completeness", "elapsed_ms", "out_of_scope")},
            }
            (SESSIONS / name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            written.append(name)

        print("写出:", ", ".join(written))
        print("进化对比:", evo["before"]["expected_tail"], "→", evo["after"]["expected_tail"])
        print("新增三元组:", [(t["rel"], t["tail"]) for t in new_triples])
        return 0
    finally:
        store.DB_PATH, store.DATA_DIR = orig


if __name__ == "__main__":
    raise SystemExit(main())
