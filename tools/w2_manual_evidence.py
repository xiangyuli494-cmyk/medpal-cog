#!/usr/bin/env python
"""W2 三项 MANUAL 证据采集（M-1 / M-2 / M-3）。

M-1、M-2 可在有 Docker 的机器上一键跑；M-3 需要人在 Nexent 控制台点一次，
把回答原文存成文本文件，再由本脚本校验三行固定格式。

用法：
    python tools/w2_manual_evidence.py --m3-transcript tmp/m3.txt
    python tools/w2_manual_evidence.py --skip-m3          # 只采 M-1/M-2

产出：
    docs/handoff/evidence/W2-manual-<YYYYMMDD-HHMM>.md
    docs/handoff/evidence/W2-manual-<YYYYMMDD-HHMM>.json
退出码：三项全 PASS 为 0，否则 1（M-3 跳过按 FAIL 记）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "handoff" / "evidence"
FENCE = chr(96) * 3

INIT_PAYLOAD = (
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
    '{"protocolVersion":"2025-06-18","capabilities":{},'
    '"clientInfo":{"name":"probe","version":"0"}}}'
)
FIXED_LINES = ("科室：", "检查项：", "完整率：")


def run(cmd, timeout=90):
    """跑命令，返回 (exit code, 合并输出)。找不到命令时返回 127。"""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "command not found: " + str(cmd[0])
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ss: %s" % (timeout, " ".join(cmd))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check_m1(expect):
    code, out = run(["docker", "ps", "-q"])
    ids = [x for x in out.splitlines() if re.fullmatch(r"[0-9a-f]{12,64}", x.strip())]
    names = []
    if code == 0 and ids:
        code2, out2 = run(["docker", "ps", "--format", "{{.Names}}"])
        if code2 == 0:
            names = [x.strip() for x in out2.splitlines() if x.strip()]
    ok = code == 0 and len(ids) >= expect
    return {
        "id": "M-1",
        "ok": ok,
        "title": "容器数",
        "detail": "docker ps -q → %d 个容器（要求 ≥%d）" % (len(ids), expect),
        "raw": out.strip()[:2000],
        "names": names,
    }


def check_m2(mcp_url):
    """优先在容器里 curl（模拟 Nexent 运行时视角），失败再退回宿主机 curl。"""
    body = INIT_PAYLOAD
    container_cmd = [
        "docker", "run", "--rm",
        "--add-host=host.docker.internal:host-gateway",
        "curlimages/curl:8.10.1", "-s", "--max-time", "20",
        "-X", "POST", mcp_url,
        "-H", "content-type: application/json",
        "-H", "accept: application/json, text/event-stream",
        "-d", body,
    ]
    code, out = run(container_cmd, timeout=180)
    mode = "container"
    if code != 0 or "medpal-cog" not in out:
        host_cmd = [
            "curl", "-s", "--max-time", "15",
            "-X", "POST", mcp_url,
            "-H", "content-type: application/json",
            "-H", "accept: application/json, text/event-stream",
            "-d", body,
        ]
        code2, out2 = run(host_cmd)
        if "medpal-cog" in out2:
            code, out, mode = code2, out2, "host"
    ok = "medpal-cog" in out
    return {
        "id": "M-2",
        "ok": ok,
        "title": "MCP 远程可达",
        "detail": "%s curl %s → serverInfo.name=%s"
        % (mode, mcp_url, "medpal-cog" if ok else "未命中"),
        "raw": out.strip()[:2000],
    }


def check_m3(console_url, transcript):
    code, out = run(["curl", "-s", "-o", "", "-w", "%{http_code}", "--max-time", "8", console_url])
    http = out.strip().splitlines()[-1] if out.strip() else ""
    text = ""
    if transcript and transcript.exists():
        text = transcript.read_text(encoding="utf-8", errors="replace")
    missing = [k for k in FIXED_LINES if k not in text]
    ok = http in {"200", "307", "302"} and not missing
    return {
        "id": "M-3",
        "ok": ok,
        "title": "控制台工具可见 + 三行格式",
        "detail": "控制台 %s → HTTP %s；回答三行缺失：%s"
        % (console_url, http, "、".join(missing) if missing else "无"),
        "raw": text.strip()[:3000],
    }


def render(results, stamp):
    lines = [
        "# W2 三项 MANUAL 证据（%s）" % stamp,
        "",
        "> 由 tools/w2_manual_evidence.py 生成。M-1/M-2 为命令实测，M-3 为控制台回答原文校验。",
        "",
        "| 项 | 内容 | 结果 | 证据 |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            "| %s | %s | %s | %s |"
            % (r["id"], r["title"], "PASS" if r["ok"] else "FAIL", r["detail"])
        )
    lines += ["", "## 原始输出", ""]
    for r in results:
        lines.append("### %s %s" % (r["id"], r["title"]))
        lines.append("")
        lines.append(FENCE + "text")
        lines.append((r.get("raw") or "(空)").strip())
        lines.append(FENCE)
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="W2 MANUAL 证据采集")
    ap.add_argument("--expect-containers", type=int, default=13)
    ap.add_argument("--mcp-url", default="http://host.docker.internal:8090/mcp")
    ap.add_argument("--console-url", default="http://localhost:3000")
    ap.add_argument("--m3-transcript", type=Path, default=None)
    ap.add_argument("--skip-m3", action="store_true", help="只采 M-1/M-2（M-3 记为未跑）")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    if shutil.which("docker") is None:
        print("[WARN] 找不到 docker 命令，M-1/M-2 会记 FAIL")

    results = [check_m1(args.expect_containers), check_m2(args.mcp_url)]
    if args.skip_m3:
        results.append(
            {
                "id": "M-3",
                "ok": False,
                "title": "控制台工具可见 + 三行格式",
                "detail": "按 --skip-m3 跳过，记为未跑",
                "raw": "",
            }
        )
    else:
        results.append(check_m3(args.console_url, args.m3_transcript))

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    md = (args.out_dir / ("W2-manual-%s.md" % stamp)).resolve()
    js = (args.out_dir / ("W2-manual-%s.json" % stamp)).resolve()
    md.write_text(render(results, stamp), encoding="utf-8", newline="\n")
    js.write_text(
        json.dumps({"stamp": stamp, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    for r in results:
        print("[%s] %s %s — %s" % ("PASS" if r["ok"] else "FAIL", r["id"], r["title"], r["detail"]))
    print("证据已写入 %s / %s" % (md.relative_to(ROOT).as_posix(), js.name))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
