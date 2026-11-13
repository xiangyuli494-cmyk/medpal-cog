"""验收自检：把 docs/冲刺计划-1130.md §10 的验收项变成可执行判定。

用法：
    python tools/acceptance.py                  # baseline：结构不变量，随时应全绿
    python tools/acceptance.py --stage w1       # 加 W1 闸门阈值（三元组/评测条数）
    python tools/acceptance.py --with-eval      # 跑离线评测并按 §10.6 套指标阈值
    python tools/acceptance.py --stage final --with-eval

FAIL 非零退出。三项 MANUAL 需要 Docker daemon，只打印命令不参与判定。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))
PY = sys.executable

# 周闸门阈值，逐项对齐 docs/冲刺计划-1130.md §3 / §10.4 / §10.6：
#   W1 三元组 ≥35、评测 ≥20；W2 ≥50 / ≥24 且版本 ≥2；W3 ≥50 / ≥30；final 与 W3 同档
STAGE_MIN = {
    "baseline": {"triples": 17, "dataset": 14, "versions": 1, "assets": 1},
    "w1": {"triples": 35, "dataset": 20, "versions": 1, "assets": 61},
    "w2": {"triples": 50, "dataset": 24, "versions": 2, "assets": 61},
    "w3": {"triples": 50, "dataset": 30, "versions": 2, "assets": 61},
    "final": {"triples": 50, "dataset": 30, "versions": 2, "assets": 61},
}

# 10 个 MCP 工具名契约（与 docs/赛题3-方案-v1.2.md §6.2、mcp-server/server.py 一致）
TOOL_CONTRACT = [
    "ingest_asset",
    "get_asset_card",
    "kg_query",
    "onto_propose",
    "onto_commit",
    "std_align",
    "trace_write",
    "skill_export",
    "kb_search",
    "health",
]

# 指标下限：(baseline, 周闸门, 交付)
METRICS = {
    "accuracy_dept": (0.95, 0.90, 0.85),
    "accuracy_exam": (0.95, 0.85, 0.80),
    "exams_strict": (0.95, 0.70, 0.65),
    "conflict_recall": (0.90, 0.85, 0.80),
    "evidence_recall": (0.95, 0.90, 0.85),
    "trace_completeness": (0.95, 0.90, 0.85),
}
LATENCY_MS = (4000, 6000, 8000)
SAME_FLOOR = 0.95
IDS = {
    "accuracy_dept": "B-01",
    "accuracy_exam": "B-02",
    "exams_strict": "B-03",
    "conflict_recall": "B-04",
    "evidence_recall": "B-05",
    "trace_completeness": "B-06",
}  # §10.6 同口径不回退：v0 的 14 条任何时候重跑都不得低于此值

REQUIRED = [
    "README.md",
    "docs/冲刺计划-1130.md",
    "docs/任务卡-三人版.md",
    "docs/env.md",
    "docs/mcp-contract.md",
    "docs/ontology-schema.md",
    "docs/charter.md",
    "docs/rules.md",
    "docs/trace-schema.md",
    "docs/judge-guide.md",
    "docs/backlog.md",
    "docs/git-flow.md",
    "docs/T3-可视化输入契约.md",
    "mcp-server/server.py",
    "skeleton.py",
    "ontology/diff.py",
    "mcp-server/parsers.py",
    "tests/test_pdf_parser.py",
    "web/trace.html",
    "agent/prompt.md",
    "agent/config.json",
    "agent/README.md",
    "agent/sessions/real-w1-01.json",
    "tools/onto_diff.py",
]

MANUAL = [
    ("M-1", "容器数", "docker ps -q | wc -l  →  ≥13"),
    (
        "M-2",
        "MCP 远程可达",
        "容器内 curl -s -X POST http://host.docker.internal:8090/mcp "
        '-H "content-type: application/json" '
        '-d \'{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":'
        '{"name":"probe","version":"0"}}}\'  →  serverInfo.name=medpal-cog',
    ),
    ("M-3", "控制台工具可见", "http://localhost:3000 工具列表 = 10 个；一次对话回答含三行固定格式"),
]


def tier(stage: str) -> int:
    if stage == "baseline":
        return 0
    return 2 if stage == "final" else 1


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    for key in ("NO_PROXY", "no_proxy"):
        cur = env.get(key, "")
        env[key] = ",".join(x for x in (cur, "127.0.0.1", "localhost") if x)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def tail(proc: subprocess.CompletedProcess) -> str:
    out = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    return out[-1][:100] if out else "无输出"


def db_stats() -> dict:
    import store

    conn = store.connect()
    try:

        def one(sql: str) -> int:
            row = conn.execute(sql).fetchone()
            return int(row[0]) if row else 0

        cur = conn.execute("SELECT version FROM version WHERE is_current=1").fetchone()
        return {
            "assets": one("SELECT COUNT(*) FROM asset"),
            "triples": one("SELECT COUNT(*) FROM triple WHERE status='active'"),
            "anchored": one(
                "SELECT COUNT(*) FROM triple WHERE status='active' "
                "AND anchor_id IS NOT NULL AND anchor_id<>''"
            ),
            "versions": one("SELECT COUNT(*) FROM version"),
            "current": cur[0] if cur else "-",
        }
    finally:
        conn.close()


def run_eval(dataset: Path) -> dict:
    if not dataset.exists():
        return {"error": f"数据集不存在：{dataset.name}"}
    with tempfile.TemporaryDirectory() as td:
        proc = run([PY, "eval/run_eval.py", "--dataset", str(dataset), "--out", td])
        if proc.returncode != 0:
            return {"error": tail(proc)}
        files = sorted(Path(td).glob("eval-*.json"))
        if not files:
            return {"error": "评测没产出报告"}
        return json.loads(files[-1].read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="baseline", choices=list(STAGE_MIN))
    ap.add_argument("--with-eval", action="store_true", help="跑评测并套指标阈值")
    ap.add_argument("--no-seed", action="store_true", help="不重建种子库，直接读现有库")
    args = ap.parse_args(argv)

    # 判定必须建立在「按当前代码重建的库」上：读一份过期的本地库，
    # 会把「代码没问题、库没重建」报成结构不变量失败。
    #
    # 第三步 publish.py：W2 闸门要求 version 表 ≥2 行（v0.9 + v1.0）、且 v1.0 有快照文件。
    # 只跑 seed + ingest 时流水线长出来的关系是「已入 triples 表、但没发布成版本」，
    # v1.0 就永远不存在——这一步把它正式定格，`diff_versions(v0.9,v1.0)` 才有得回放。
    if not args.no_seed:
        for step in (
            ["mcp-server/seed.py", "--reset"],
            ["tools/ingest_all.py"],
            ["mcp-server/publish.py", "--version", "v1.0", "--note", "W2 本体：表格与指南抽取"],
        ):
            sd = run([PY, *step])
            if sd.returncode != 0:
                print(f"[FAIL] 建库失败：{step[0]} → {tail(sd)}")
                return 2

    t = tier(args.stage)
    need = STAGE_MIN[args.stage]
    rows: list[tuple[str, str, bool | None, str]] = []

    def add(cid: str, name: str, ok: bool | None, detail: str) -> None:
        rows.append((cid, name, ok, detail))

    tests = run([PY, "-m", "pytest", "tests"])
    add(
        "A-01",
        "pytest 全绿",
        tests.returncode == 0,
        "退出码 0" if tests.returncode == 0 else tail(tests),
    )

    sk = run([PY, "skeleton.py"])
    add("A-02", "骨架五步跑通", sk.returncode == 0, "OK" if sk.returncode == 0 else tail(sk))

    # A-03 判两件事：工具名与契约一致（10 个，不多不少）+ 评估器四道闸能过
    srv = (ROOT / "mcp-server/server.py").read_text(encoding="utf-8")
    registered = re.findall(r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\s*\(", srv)
    missing_tools = [n for n in TOOL_CONTRACT if n not in registered]
    extra_tools = [n for n in registered if n not in TOOL_CONTRACT]
    ct = run([PY, "tools/check_evaluator.py"])
    # 智能体配置里的白名单也得和契约同源，否则平台侧会挂到已改名的工具上
    try:
        cfg = json.loads((ROOT / "agent" / "config.json").read_text(encoding="utf-8"))
        cfg_tools = set(cfg["tools"]["mcp"])
    except Exception:
        cfg_tools = set()
    whitelist_ok = cfg_tools == set(TOOL_CONTRACT)
    tool_ok = not missing_tools and not extra_tools and whitelist_ok
    add(
        "A-03",
        "10 工具契约（服务端 + 智能体白名单 + 评估器四道闸）",
        tool_ok and ct.returncode == 0,
        (
            "名字齐且白名单一致"
            if tool_ok
            else (
                f"缺 {missing_tools} 多 {extra_tools} "
                f"白名单差 {sorted(cfg_tools ^ set(TOOL_CONTRACT))}"
            )
        )
        + "；评估器 "
        + ("过" if ct.returncode == 0 else tail(ct)),
    )

    try:
        st = db_stats()
        db_ok = True
        db_err = ""
    except Exception as exc:  # 库不存在或缺表
        st = {"assets": 0, "triples": 0, "anchored": 0, "versions": 0, "current": "-"}
        db_ok = False
        db_err = f"{type(exc).__name__}: {exc}"[:100]

    add("A-04", "种子库可查", db_ok, f"{st['assets']} 卡" if db_ok else db_err)
    cards = len(list((ROOT / "data/asset-cards").glob("*.json")))
    add("A-05", "资产卡 ≥61 张", cards >= 61, f"{cards} 张")
    add(
        "A-06",
        f"Asset Card 入库 ≥{need['assets']}",
        st["assets"] >= need["assets"],
        f"{st['assets']} 行（tools/ingest_all.py）",
    )
    add(
        "A-07",
        f"活跃三元组 ≥{need['triples']}",
        st["triples"] >= need["triples"],
        f"{st['triples']} 条",
    )
    add(
        "A-08",
        "三元组全部带锚点",
        st["triples"] > 0 and st["anchored"] == st["triples"],
        f"{st['anchored']}/{st['triples']}",
    )
    add(
        "A-09",
        f"本体快照 ≥{need['versions']} 个",
        st["versions"] >= need["versions"],
        f"{st['versions']} 个，当前 {st['current']}",
    )

    samples = {
        d.name: len(list(d.iterdir()))
        for d in sorted((ROOT / "data/samples").iterdir())
        if d.is_dir()
    }
    # 三类各 ≥20；以后加 pdf/ 等新模态目录不算违规（只增不减）
    ok = all(samples.get(k, 0) >= 20 for k in ("text", "table", "image"))
    add(
        "A-10",
        "三类样本各 ≥20",
        ok,
        "/".join(str(samples.get(k, 0)) for k in ("text", "table", "image")),
    )

    skills = [d for d in (ROOT / "skills").iterdir() if d.is_dir()]
    with_md = [d for d in skills if (d / "SKILL.md").exists()]
    add(
        "A-11",
        "三个 Skill 包齐",
        len(skills) == 3 and len(with_md) == 3,
        f"{len(with_md)}/{len(skills)} 有 SKILL.md",
    )

    tools = (ROOT / "mcp-server/server.py").read_text(encoding="utf-8")
    n_tools = len(re.findall(r"@mcp\.tool", tools))
    add("A-12", "MCP 工具 10 个", n_tools == 10, str(n_tools))

    missing = [f for f in REQUIRED if not (ROOT / f).exists()]
    add(
        "A-13",
        f"必备文档/入口齐（{len(REQUIRED)} 项）",
        not missing,
        "全在" if not missing else "缺 " + ", ".join(missing[:3]),
    )

    ds = (
        ROOT
        / "eval/dataset"
        / ("v1.jsonl" if (ROOT / "eval/dataset/v1.jsonl").exists() else "v0.jsonl")
    )
    n_rows = sum(1 for line in ds.read_text(encoding="utf-8").splitlines() if line.strip())
    add(
        "A-14",
        f"评测集 ≥{need['dataset']} 条",
        n_rows >= need["dataset"],
        f"{ds.name} {n_rows} 条",
    )

    env_tracked = run(["git", "ls-files", ".env"])
    add(
        "A-15",
        ".env 未入库",
        not (env_tracked.stdout or "").strip(),
        (env_tracked.stdout or "").strip() or "干净",
    )

    big = []
    files = run(["git", "ls-files"])
    for rel in (files.stdout or "").splitlines():
        fp = ROOT / rel
        if fp.is_file() and fp.stat().st_size > 2 * 1024 * 1024:
            big.append(f"{rel} {fp.stat().st_size // 1024 // 1024}MB")
    add("A-16", "无 >2MB 文件入库", not big, "干净" if not big else "; ".join(big[:3]))

    if args.with_eval:
        rep = run_eval(ds)
        if "error" in rep:
            add("B-00", "评测可运行", False, rep["error"])
        else:
            add("B-00", "评测可运行", True, f"n={rep['n']}，{rep['avg_latency_ms']} ms/题")
            for field, vals in METRICS.items():
                got = float(rep.get(field, 0.0))
                add(
                    IDS[field],
                    f"{field} ≥{vals[t]:.2f}",
                    got >= vals[t],
                    f"{got:.3f}",
                )
            lat = float(rep.get("avg_latency_ms", 1e9))
            add("B-07", f"平均时延 ≤{LATENCY_MS[t]} ms", lat <= LATENCY_MS[t], f"{lat:.0f} ms")

            same = run_eval(ROOT / "eval/dataset/v0.jsonl")
            if "error" in same:
                add("B-S0", "同口径 v0 重跑", False, same["error"])
            else:
                pairs = [(f, float(same.get(f, 0.0))) for f in METRICS]
                worst = min(pairs, key=lambda kv: kv[1])
                add(
                    "B-08",
                    f"同口径不回退 ≥{SAME_FLOOR:.2f}",
                    worst[1] >= SAME_FLOOR,
                    f"最低 {worst[1]:.3f}（{worst[0]}）",
                )

    width = max(len(r[1]) for r in rows)
    print(f"验收档位：{args.stage}（评测阈值 {'套用' if args.with_eval else '未跑'}）")
    print("-" * 72)
    for cid, name, ok, detail in rows:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {cid} {name.ljust(width)} ｜ {detail}")
    print("-" * 72)
    for mid, name, cmd in MANUAL:
        print(f"[MANUAL] {mid} {name}：{cmd}")
    failed = [r for r in rows if not r[2]]
    print("-" * 72)
    print(f"PASS {len(rows) - len(failed)} / FAIL {len(failed)} / MANUAL {len(MANUAL)}")
    if failed:
        print("未通过：" + "、".join(f"{r[0]}({r[1]})" for r in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
