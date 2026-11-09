"""W2 T3-1：PDF 解析链路 24 条评测（离线、可复现、带六项基线）。

与 `eval/run_eval.py`（问诊 20 题）的分工：
  - run_eval.py 评「S3 决策链在离线复现下的分数」
  - 本脚本评「ingest_asset / PdfParser 这条解析链路本身」

沿用同一条临时库约定：每次运行现建自己的库，不碰 mcp-server/data/medpal.db，
否则跑一次就往交付库塞几十张卡，台账条数漂移、重复跑也不可比。

六项基线：
  准确率（24 条通过率）、精确率 / 召回 / F1（正常件与异常件的判定）、
  稳定性（同一进程连跑两轮逐条判定一致）、可复现性（两轮聚合分完全相等）、
  降级成功率（异常件全部 ok=false + 合法 reason + 非空 hint，且不抛异常）。

用法：
  python tools/gen_pdf_fixtures.py      # 先生成样本（tmp/ 下，gitignore）
  python eval/run_pdf_eval.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

FIXTURES = ROOT / "tmp" / "pdf-fixtures"
DATASET = ROOT / "eval" / "dataset" / "pdf_w2_24.jsonl"
REPORT_DIR = ROOT / "eval" / "reports"

# docs/mcp-contract.md §3 的错误码总表；异常件只能从这里取值
ALLOWED_REASONS = {
    "file_not_found",
    "no_parser",
    "parser_unavailable",
    "asset_not_found",
    "diff_not_found",
    "triple_not_found",
    "empty_input",
    "unmapped",
    "empty_steps",
    "trace_not_found",
    "kb_not_configured",
    "no_seed",
    "no_path",
}


class Ctx:
    """一轮评测的运行上下文：一个临时库 + 一组调用助手。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        os.environ["MEDPAL_DB"] = str(db_path)
        import parsers  # noqa: PLC0415
        import server  # noqa: PLC0415
        import store  # noqa: PLC0415

        self.parsers, self.server, self.store = parsers, server, store

    def ingest(self, name: str, **kw) -> dict:
        """调 ingest_asset；任何异常都折成 ok=false + raised=True，供降级项判定。"""
        path = str(FIXTURES / name)
        t0 = time.time()
        try:
            out = dict(self.server.ingest_asset(path=path, **kw))
            out["_raised"] = False
        except Exception as exc:  # noqa: BLE001 - 评测要把异常本身算作失败证据
            out = {
                "ok": False,
                "reason": "exception",
                "hint": "",
                "_raised": True,
                "_exc": f"{type(exc).__name__}: {exc}",
            }
        out["_ms"] = int((time.time() - t0) * 1000)
        return out

    def ingest_path(self, path: Path) -> dict:
        try:
            out = dict(self.server.ingest_asset(path=str(path)))
            out["_raised"] = False
        except Exception as exc:  # noqa: BLE001
            out = {"ok": False, "reason": "exception", "_raised": True,
                   "_exc": f"{type(exc).__name__}: {exc}"}
        return out

    def parse(self, name: str):
        return self.parsers.parse(FIXTURES / name)

    def asset_count(self) -> int:
        conn = self.store.connect()
        try:
            return len(self.store.list_assets(conn, limit=10000))
        finally:
            conn.close()


def _anchor_ids(res: dict) -> list[str]:
    return [a.get("anchor_id", "") for a in res.get("anchors") or []]


def _fail_reason(res: dict) -> str:
    if res.get("_raised"):
        return "抛异常 " + str(res.get("_exc", ""))
    if res.get("ok") is not False:
        return "本应失败却返回 ok=true"
    if res.get("reason") not in ALLOWED_REASONS:
        return f"reason 越界：{res.get('reason')!r}"
    if not res.get("hint"):
        return "hint 为空（契约要求失败必须给提示）"
    return ""


# ---------- 24 条用例：id -> 检查函数 ----------


BODY_PROBES = ("主诉", "查体", "辅助检查", "处理", "随访", "说明")


def c01_normal_single(ctx: Ctx):
    r = ctx.ingest("normal_1page.pdf")
    if not r.get("ok"):
        return False, f"正常件解析失败：{r.get('reason')} {r.get('hint', '')}"
    if len(r.get("anchors") or []) < 1:
        return False, "无锚点，无法溯源"
    # 「不丢字」看的是文本覆盖率，不是块数：一页 6 行正文合成 1 个段落块是正常切法。
    body = "\n".join(b.text for b in ctx.parse("normal_1page.pdf").blocks)
    missing = [p for p in BODY_PROBES if p not in body]
    if missing:
        return False, f"文本丢失：{missing}"
    return True, f"blocks={r['blocks']} anchors={len(r['anchors'])}，6 段文字全覆盖"


def c02_normal_multi(ctx: Ctx):
    r = ctx.ingest("normal_3page.pdf")
    if not r.get("ok"):
        return False, f"多页件解析失败：{r.get('reason')}"
    pages = {m.group(1) for a in _anchor_ids(r) if (m := re.search(r"#p(\d+)\.", a))}
    if pages != {"1", "2", "3"}:
        return False, f"页锚点不全：{sorted(pages)}"
    return True, f"页锚点 {sorted(pages)}"


def c03_heading(ctx: Ctx):
    d = ctx.parse("heading_doc.pdf")
    kinds = [b.kind for b in d.blocks]
    if kinds.count("heading") < 2:
        return False, f"章节标题识别不足：{kinds}"
    if "paragraph" not in kinds:
        return False, f"标题下的正文没切成段落：{kinds}"
    return True, f"heading={kinds.count('heading')} paragraph={kinds.count('paragraph')}"


def c04_table(ctx: Ctx):
    r = ctx.ingest("table_doc.pdf")
    if not r.get("ok"):
        return False, f"表格件解析失败：{r.get('reason')}"
    rows = [a for a in _anchor_ids(r) if re.search(r"#p\d+\.t\d+\.r\d+$", a)]
    if len(rows) < 2:
        return False, f"表格行锚点不足：{len(rows)}"
    return True, f"table_row 锚点 {len(rows)} 条"


def c05_blank_page(ctx: Ctx):
    r = ctx.ingest("blank_mixed.pdf")
    if not r.get("ok"):
        return False, f"含空白页的文件解析失败：{r.get('reason')}"
    ids = _anchor_ids(r)
    if any("#p2." in a for a in ids):
        return False, "空白页产生了锚点（会污染溯源）"
    if not any("#p1." in a for a in ids):
        return False, "第 1 页文本丢失"
    if not any("#p3." in a for a in ids):
        return False, "第 3 页文本丢失"
    return True, f"跳空白页正常，共 {len(ids)} 锚点"


def c06_no_text_layer(ctx: Ctx):
    """扫描件（无文字层）：按「无原生文本」规范化降级，不许建 0 块的空卡。

    这条最初写成「ok + 0 块」，是把「能解析」和「该入库」混为一谈：
    0 块的资产卡没有任何锚点，溯源点不回去，等于往台账里塞一张空卡。
    main 的处理是 ok=false + parser_unavailable + hint 说明无原生文本，
    行为和契约 §1.1 一致，评测期望按它订正。
    """
    before = ctx.asset_count()
    r = ctx.ingest("image_only.pdf")
    why = _fail_reason(r)
    if why:
        return False, why
    if r.get("reason") != "parser_unavailable":
        return False, f"reason 应为 parser_unavailable：{r.get('reason')!r}"
    if "文本" not in (r.get("hint") or ""):
        return False, f"hint 未说明无原生文本：{r.get('hint')!r}"
    if ctx.asset_count() != before:
        return False, "无文字层文件仍写了资产卡（幽灵卡）"
    return True, f"扫描件规范化降级：{r.get('hint')}"


def c07_special_chars(ctx: Ctx):
    r = ctx.ingest("special_chars.pdf")
    if not r.get("ok"):
        return False, f"符号件解析失败：{r.get('reason')}"
    text = "".join(a.get("text", "") for a in r.get("anchors") or [])
    missing = [ch for ch in ("≥", "±") if ch not in text]
    if missing:
        return False, f"符号丢失/乱码：{missing}"
    return True, "≥ ± 等符号保留"


def c08_long_text(ctx: Ctx):
    d = ctx.parse("long_text.pdf")
    kinds = [b.kind for b in d.blocks]
    paras = [b for b in d.blocks if b.kind == "paragraph"]
    if not paras:
        return False, f"整页正文被判成标题：heading={kinds.count('heading')} paragraph=0"
    if len(paras) < 8:
        return False, f"分段太少：paragraph={len(paras)}（整页正文没有断块）"
    longest = max(len(b.text) for b in paras)
    if longest > 1200:
        return False, f"单块 {longest} 字，超过 1200 字上限，检索切不开也召不准"
    if not any("第 8-30 行" in b.text for b in d.blocks):
        return False, "末页最后一行丢失"
    return True, f"paragraph={len(paras)} 最长块 {longest} 字，末行保留"


def c09_nested_headings(ctx: Ctx):
    d = ctx.parse("nested_headings.pdf")
    kinds = [b.kind for b in d.blocks]
    if kinds.count("heading") < 4:
        return False, f"多级标题漏识别：{kinds}"
    if kinds.count("paragraph") < 3:
        return False, f"多级标题下正文未成段：{kinds}"
    return True, f"heading={kinds.count('heading')} paragraph={kinds.count('paragraph')}"


def _expect_fail(ctx: Ctx, name: str, must_mention: tuple[str, ...] = ()):
    r = ctx.ingest(name)
    why = _fail_reason(r)
    if why:
        return False, why
    if must_mention:
        text = (r.get("hint") or "") + (r.get("detail") or "")
        if not any(k in text for k in must_mention):
            return False, f"降级说明缺失关键词 {must_mention}：hint={r.get('hint')!r}"
    return True, f"recovered: reason={r['reason']} hint非空"


def c10_zero_byte(ctx: Ctx):
    return _expect_fail(ctx, "zero_byte.pdf")


def c11_broken(ctx: Ctx):
    return _expect_fail(ctx, "broken_header.pdf")


def c12_fake_ext(ctx: Ctx):
    return _expect_fail(ctx, "fake_ext.pdf")


def c13_encrypted(ctx: Ctx):
    return _expect_fail(ctx, "encrypted.pdf", must_mention=("加密", "密码", "encrypt"))


def c14_not_found(ctx: Ctx):
    r = ctx.ingest("missing_does_not_exist.pdf")
    if r.get("_raised"):
        return False, "缺文件时抛异常"
    if r.get("ok") is not False or r.get("reason") != "file_not_found":
        return False, f"reason 应为 file_not_found，实为 {r.get('reason')}"
    if "missing_does_not_exist.pdf" not in (r.get("hint") or ""):
        return False, "hint 未回显路径，Agent 无法纠错"
    return True, "file_not_found + 回显路径"


def c15_unsupported(ctx: Ctx):
    r = ctx.ingest("unsupported.xyz")
    if r.get("_raised"):
        return False, "无解析器时抛异常"
    if r.get("ok") is not False or r.get("reason") != "no_parser":
        return False, f"reason 应为 no_parser，实为 {r.get('reason')}"
    return True, "no_parser"


def c16_anchor_contract(ctx: Ctx):
    r = ctx.ingest("normal_3page.pdf")
    if not r.get("ok"):
        return False, f"取锚点失败：{r.get('reason')}"
    aid = r["asset_id"]
    bad = [a for a in r["anchors"] if not {"anchor_id", "kind", "text"} <= set(a)]
    if bad:
        return False, f"锚点字段缺失：{bad[0]}"
    prefix_bad = [a["anchor_id"] for a in r["anchors"] if not a["anchor_id"].startswith(aid + "#")]
    if prefix_bad:
        return False, f"锚点未挂 asset_id：{prefix_bad[:2]}"
    ids = _anchor_ids(r)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        return False, f"锚点 id 重复（同一位置被引用两次）：{dups}"
    return True, f"{len(ids)} 条锚点格式合规且唯一"


def c17_asset_id(ctx: Ctx):
    r = ctx.ingest("normal_1page.pdf")
    if not r.get("ok"):
        return False, f"入库失败：{r.get('reason')}"
    if not re.fullmatch(r"AST-\d{4}-[0-9a-f]{6}", r["asset_id"]):
        return False, f"资产号不合规：{r['asset_id']}"
    return True, r["asset_id"]


def c18_stable(ctx: Ctx):
    d1 = ctx.parse("normal_3page.pdf")
    d2 = ctx.parse("normal_3page.pdf")
    ids1, ids2 = [a["anchor_id"] for a in d1.anchors], [a["anchor_id"] for a in d2.anchors]
    if ids1 != ids2:
        return False, "同一文件两次解析锚点漂移"
    same = ctx.ingest("normal_3page.pdf")
    again = ctx.ingest("normal_3page.pdf")
    if same.get("asset_id") != again.get("asset_id"):
        return False, "同一文件两次入库资产号不固定"
    return True, f"锚点 {len(ids1)} 条稳定，资产号 {same['asset_id']} 固定"


def c19_concurrency(ctx: Ctx):
    results, errors = [], []

    def worker():
        try:
            results.append(ctx.ingest("normal_3page.pdf"))
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors or len(results) != 4:
        return False, f"并发调用异常：{errors[:2]}"
    if not all(r.get("ok") for r in results):
        return False, "并发中有请求失败"
    counts = {len(r.get("anchors") or []) for r in results}
    if len(counts) != 1:
        return False, f"并发结果不一致（状态污染）：{sorted(counts)}"
    return True, f"4 并发全部 ok，锚点均为 {counts.pop()} 条"


def c20_large(ctx: Ctx):
    r = ctx.ingest("long_text.pdf")
    if not r.get("ok"):
        return False, f"长文档解析失败：{r.get('reason')}"
    expect = len(ctx.parse("long_text.pdf").blocks)
    if r.get("blocks") != expect:
        return False, f"入库块数 {r.get('blocks')} 与解析块数 {expect} 不一致（有截断）"
    if r["_ms"] > 15000:
        return False, f"耗时过长 {r['_ms']} ms"
    return True, f"8 页 {expect} 块，{r['_ms']} ms"


def c21_ledger_card(ctx: Ctx):
    r = ctx.ingest("normal_1page.pdf")
    if not r.get("ok"):
        return False, f"入库失败：{r.get('reason')}"
    card = ctx.server.get_asset_card(asset_id=r["asset_id"])
    if not card.get("ok") or not card.get("cards"):
        return False, f"台账查不到卡片：{card.get('reason')}"
    c = card["cards"][0]
    if c.get("modality") != "pdf_text":
        return False, f"模态错：{c.get('modality')}"
    if len(c.get("anchors") or []) != len(r["anchors"]):
        return False, "卡片锚点数与解析结果不一致"
    return True, f"卡片 {c['asset_id']} modality=pdf_text anchors={len(c['anchors'])}"


def c22_ledger_no_ghost(ctx: Ctx):
    before = ctx.asset_count()
    r = ctx.ingest("broken_header.pdf")
    after = ctx.asset_count()
    if r.get("_raised"):
        return False, "坏文件抛异常（会中断批量入库）"
    if r.get("ok"):
        return False, "坏文件被判成功，会往台账塞假卡"
    if after != before:
        return False, f"失败也写卡：{before} -> {after}"
    return True, f"失败未写卡（台账仍 {after} 张）"


def c23_batch_unique(ctx: Ctx):
    files = sorted((FIXTURES / "batch").glob("batch_*.pdf"))
    if len(files) < 10:
        return False, f"批量样本不足：{len(files)}"
    ids, fails = [], []
    for f in files:
        r = ctx.ingest_path(f)
        if r.get("ok"):
            ids.append(r["asset_id"])
        else:
            fails.append(f"{f.name}:{r.get('reason')}")
    if fails:
        return False, f"批量中有失败：{fails[:3]}"
    if len(set(ids)) != len(ids):
        return False, f"资产号重复：{len(ids)} 份 -> {len(set(ids))} 个号"
    return True, f"{len(ids)} 份 -> {len(set(ids))} 个唯一资产号"


def c24_degrade_detail(ctx: Ctx):
    names = ["zero_byte.pdf", "broken_header.pdf", "fake_ext.pdf", "encrypted.pdf"]
    bad = []
    for n in names:
        r = ctx.ingest(n)
        why = _fail_reason(r)
        if why:
            bad.append(f"{n}: {why}")
    if bad:
        return False, "; ".join(bad[:3])
    return True, f"{len(names)} 个异常件全部规范化降级"


CHECKS = {
    1: c01_normal_single,
    2: c02_normal_multi,
    3: c03_heading,
    4: c04_table,
    5: c05_blank_page,
    6: c06_no_text_layer,
    7: c07_special_chars,
    8: c08_long_text,
    9: c09_nested_headings,
    10: c10_zero_byte,
    11: c11_broken,
    12: c12_fake_ext,
    13: c13_encrypted,
    14: c14_not_found,
    15: c15_unsupported,
    16: c16_anchor_contract,
    17: c17_asset_id,
    18: c18_stable,
    19: c19_concurrency,
    20: c20_large,
    21: c21_ledger_card,
    22: c22_ledger_no_ghost,
    23: c23_batch_unique,
    24: c24_degrade_detail,
}


def load_dataset(path: Path) -> list[dict]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 24:
        raise SystemExit(f"数据集应为 24 条，实为 {len(rows)} 条：{path}")
    missing = [r["id"] for r in rows if r["id"] not in CHECKS]
    if missing:
        raise SystemExit(f"数据集里的用例没有实现检查函数：{missing}")
    return rows


def run_once(rows: list[dict], db_path: Path) -> dict:
    ctx = Ctx(db_path)
    details = []
    for row in rows:
        t0 = time.time()
        try:
            passed, note = CHECKS[row["id"]](ctx)
        except Exception as exc:  # noqa: BLE001 - 检查函数自己出错也算失败
            tail = traceback.format_exception_only(type(exc), exc)[-1].strip()
            passed, note = False, "检查函数异常：" + tail
        details.append(
            {
                "id": row["id"],
                "name": row["name"],
                "locked": row["locked"],
                "expect": row["expect"],
                "group": row.get("group", "normal"),
                "degrade": bool(row.get("degrade")),
                "passed": bool(passed),
                "note": note,
                "ms": int((time.time() - t0) * 1000),
            }
        )
    return {"details": details}


def metrics(details: list[dict]) -> dict:
    """六项基线里可算的五项（稳定性/可复现性由两轮比对得出）。

    正例取「异常件」：解析链路最该保证的不是把好文件读出来，而是**坏文件不许炸**——
    炸一次整个批量入库就中断，Agent 侧也无从纠错。所以：
      召回 = 异常件判对 / 异常件总数
      精确 = 异常件判对 / (异常件判对 + 正常件被判失败)   ← 把好文件误杀同样扣分
    """
    n = len(details)
    passed = sum(d["passed"] for d in details)
    abnormal = [d for d in details if d["group"] == "abnormal"]
    tp = sum(d["passed"] for d in abnormal)
    fp = sum(1 for d in details if d["group"] == "normal" and not d["passed"])
    recall = tp / len(abnormal) if abnormal else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    degrade_cases = [d for d in details if d["degrade"]]
    degrade = (
        sum(d["passed"] for d in degrade_cases) / len(degrade_cases) if degrade_cases else 0.0
    )

    return {
        "n": n,
        "passed": passed,
        "accuracy": round(passed / n, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "degrade_success": round(degrade, 3),
        "avg_ms": round(sum(d["ms"] for d in details) / n, 1),
    }


def stability(run_a: list[dict], run_b: list[dict]) -> float:
    same = sum(1 for a, b in zip(run_a, run_b, strict=True) if a["passed"] == b["passed"])
    return round(same / len(run_a), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--out", default=str(REPORT_DIR))
    ap.add_argument("--db", default=str(ROOT / "tmp" / "pdf-eval-scratch.db"))
    ap.add_argument("--skip-fixtures", action="store_true", help="不检查样本是否已生成")
    args = ap.parse_args()

    if not args.skip_fixtures and not (FIXTURES / "normal_1page.pdf").exists():
        print("缺样本：先跑 python tools/gen_pdf_fixtures.py")
        return 2

    rows = load_dataset(Path(args.dataset))

    db1 = Path(args.db).with_name("pdf-eval-run1.db")
    db2 = Path(args.db).with_name("pdf-eval-run2.db")
    db1.parent.mkdir(parents=True, exist_ok=True)
    for p in (db1, db2):
        if p.exists():
            p.unlink()

    run_a = run_once(rows, db1)
    run_b = run_once(rows, db2)
    m = metrics(run_a["details"])
    m["stability"] = stability(run_a["details"], run_b["details"])
    # 两轮各用独立空库：五项聚合分完全相等才算「换库/换机器跑出同一份分」
    keys = ("accuracy", "precision", "recall", "f1", "degrade_success")
    mb = metrics(run_b["details"])
    m["reproducibility"] = round(sum(1.0 for k in keys if m[k] == mb[k]) / len(keys), 3)

    tag = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {**m, "dataset": Path(args.dataset).name, "details": run_a["details"]}
    (out_dir / f"pdf-eval-{tag}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# PDF 解析链路评测 {tag}",
        "",
        f"- 数据集：{report['dataset']}（{m['n']} 条）",
        f"- 通过：{m['passed']}/{m['n']}（准确率 {m['accuracy']:.0%}）",
        f"- 精确率 {m['precision']:.0%} / 召回 {m['recall']:.0%} / F1 {m['f1']:.0%}",
        f"- 稳定性 {m['stability']:.0%} / 可复现性 {m['reproducibility']:.0%}",
        f"- 降级成功率 {m['degrade_success']:.0%}",
        f"- 平均时延 {m['avg_ms']} ms",
        "",
        "| # | 用例 | 锁定 | 期望 | 结果 | 现场 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in run_a["details"]:
        lines.append(
            f"| {d['id']} | {d['name']} | {'是' if d['locked'] else '否'} | "
            f"{d['expect']} | {'通过' if d['passed'] else '失败'} | {d['note']} |"
        )
    md = out_dir / f"pdf-eval-{tag}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines[:8]))
    print(f"\n报告：{md}")
    return 0 if m["passed"] == m["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
