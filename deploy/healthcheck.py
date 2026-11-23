"""容器健康检查：真向 /mcp 发一次 initialize，再调一次 health 工具。

端口通不算健康；只认 serverInfo.name 也不算健康——库空时服务照样「健康」，
那正是「空台账蒙混过关」（评审 #36 第 3 条）。两关都查：
  1) initialize 回 serverInfo.name=medpal-cog（§10.5 M-2 同口径）
  2) tools/call health 的 assets ≥ MEDPAL_MIN_ASSETS（默认 61 = R1 基线）

用法（容器内）：python /app/healthcheck.py  → 退出码 0 健康 / 1 不健康
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8090/mcp"
TIMEOUT = 5.0
# 61 = R1 基线（建库后 1 条种子资产 + 60 张样本卡），实测完整入库是 70 张。
# 只判 >0 会被 seed 那 1 条种子资产放过去，所以门槛按 R1 基线卡：
# 少卡和空账一样不许判健康。真要放宽用 MEDPAL_MIN_ASSETS 覆盖。
MIN_ASSETS = int(os.environ.get("MEDPAL_MIN_ASSETS") or 61)

HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


def _post(payload: dict) -> str:
    # 显式禁掉代理：探活打的是本机回环，走代理会被拒（Windows 上实测踩过）
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers=HEADERS, method="POST"
    )
    return opener.open(req, timeout=TIMEOUT).read().decode("utf-8", "replace")


def _rpc(rpc_id: int, method: str, params: dict) -> str:
    return _post({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})


def main() -> int:
    init_args = {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "healthcheck", "version": "0"},
    }
    try:
        init = _rpc(1, "initialize", init_args)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[healthcheck] FAIL 连不上 {URL}: {exc}")
        return 1

    if '"name":"medpal-cog"' not in init.replace(" ", ""):
        print(f"[healthcheck] FAIL 响应里没有 serverInfo.name=medpal-cog：{init[:160]!r}")
        return 1

    # 第二关：调 health 工具，看资产数。服务活着但台账空 → 不判健康。
    try:
        body = _rpc(2, "tools/call", {"name": "health", "arguments": {}})
    except (urllib.error.URLError, OSError) as exc:
        print(f"[healthcheck] FAIL 调 health 工具失败：{exc}")
        return 1

    m = re.search(r'"assets"\s*:\s*(\d+)', body) or re.search(r'\\"assets\\"\s*:\s*(\d+)', body)
    if not m:
        print(f"[healthcheck] FAIL health 响应里没有 assets 字段：{body[:200]!r}")
        return 1
    assets = int(m.group(1))
    if assets < MIN_ASSETS:
        print(f"[healthcheck] FAIL 台账 assets={assets} < {MIN_ASSETS}（空台账不算健康）")
        return 1

    print(f"[healthcheck] OK serverInfo.name=medpal-cog assets={assets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
