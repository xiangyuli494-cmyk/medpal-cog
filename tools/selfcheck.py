"""一键自检：种子库 → 测试 → 评测 → 骨架 → 契约校验。

用法：
    python tools/selfcheck.py            # 全跑，红了就非零退出
    python tools/selfcheck.py --fast     # 跳过评测（改文档/前端时用）

在 CI 与本地都跑这一份，避免「我这儿是好的」。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 回环请求必须绕过系统代理，否则 httpx 在 127.0.0.1 上报 502
    for key in ("NO_PROXY", "no_proxy"):
        cur = env.get(key, "")
        env[key] = ",".join(x for x in (cur, "127.0.0.1", "localhost") if x)
    return env


STEPS = [
    ("种子库", [PY, "mcp-server/seed.py", "--reset"], "17"),
    # 进化预演：v0.9 → v1.0。这一步失败说明 onto_propose/onto_commit 链断了，
    # 比测试先报更有指向性（测试里也有一条独立校验）
    ("本体进化", [PY, "mcp-server/ontology_evolve.py"], "v1.0"),
    # pytest -q 在 addopts 也是 -q 时不打汇总行，退出码即结论
    ("测试", [PY, "-m", "pytest", "tests"], None),
    ("评测", [PY, "eval/run_eval.py"], "100"),
    ("骨架", [PY, "skeleton.py"], "OK"),
    ("契约校验", [PY, "tools/check_evaluator.py"], None),
]


def _run(cmd: list, expect) -> tuple:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, f"退出码 {proc.returncode}"
    if expect and expect not in out:
        return False, f"输出里没有 {expect}"
    return True, "ok"


def main(argv: list) -> int:
    # Windows 控制台默认 GBK，输出统一走 UTF-8，避免 CI 日志乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    fast = "--fast" in argv
    steps = [s for s in STEPS if not (fast and s[0] == "评测")]

    print(f"工作目录：{ROOT}")
    print(f"解释器：{PY}")
    failed = []

    for name, cmd, expect in steps:
        ok, detail = _run(cmd, expect)
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            failed.append(name)

    if failed:
        print("")
        print(f"有 {len(failed)} 步没过：{'、'.join(failed)}")
        print("先看对应命令的原始输出，别改断言让它变绿。")
        return 1

    print("")
    print(f"全绿（{len(steps)} 步）。可以提 PR 了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
