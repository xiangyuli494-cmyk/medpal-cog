# W2 三项 MANUAL 执行单（M-1 / M-2 / M-3）

> 用途：11/15 闸门判定前补上 `acceptance.py` 的三条人工检查。
> 本机现状（11-15 01:05 实测）：`wsl -l -v` 显示 docker-desktop **Stopped**，启动报 `HCS_E_HYPERV_NOT_INSTALLED`；`docker ps` 返回 500，`http://localhost:3000` 不可达。**这台机器上跑不了，需要在 W0 装过 Nexent 的那台机器上执行。**

## 0 一条命令跑完 M-1 / M-2

```bash
# 在仓库根目录，Nexent 已启动（13 个容器在跑）的机器上
python tools/w2_manual_evidence.py --m3-transcript tmp/m3.txt
```

脚本做三件事：

| 项 | 脚本动作 | 判定 |
| --- | --- | --- |
| M-1 | `docker ps -q` 数容器 | ≥13 为 PASS |
| M-2 | `docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl ... initialize` | 返回含 `medpal-cog` 为 PASS；容器方式失败会自动退回宿主机 curl |
| M-3 | `curl localhost:3000` 状态码 + 校验 `tmp/m3.txt` 里三行 | 200/302/307 且三行齐全为 PASS |

产物写在 `docs/handoff/evidence/W2-manual-<时间戳>.md` 与同名 `.json`，退出码 0 = 三项全 PASS。

## 1 M-3 要你手动做的一步（约 3 分钟）

1. 打开 `http://localhost:3000`，登录 Nexent 控制台。
2. 确认工具列表能看到 10 个：`ingest_asset` `get_asset_card` `kg_query` `onto_propose` `onto_commit` `std_align` `trace_write` `skill_export` `kb_search` `health`。
3. 新建对话，用 v1.0 本体问一句：`最近总是上腹隐痛，饭后加重，需要挂什么科、做什么检查？`
4. 把回答**原样**贴进 `tmp/m3.txt`，必须含三行：

```text
科室：消化内科
检查项：胃镜、幽门螺杆菌检测
完整率：0.75
```

5. 再跑一次 `python tools/w2_manual_evidence.py --m3-transcript tmp/m3.txt`，三项应全 PASS。

## 2 采完怎么入库

```bash
git checkout -b docs/w2-manual-evidence origin/main
cp docs/handoff/evidence/W2-manual-*.md docs/handoff/evidence/W2-manual-*.json docs/handoff/evidence/
git add docs/handoff/evidence && git commit -m "docs(evidence): W2 三项 MANUAL 实跑证据"
git push -u origin docs/w2-manual-evidence
```

然后开 PR，标题写 `docs(evidence): W2 三项 MANUAL 实跑证据`，正文贴脚本输出的三行 PASS。

## 3 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| M-1 0 个容器 | Docker Desktop 没起 / WSL 停了 | Docker Desktop 里点 Start；仍报 `HCS_E_HYPERV_NOT_INSTALLED` 说明本机没开虚拟化，换机器 |
| M-2 容器方式超时 | `curlimages/curl` 拉不下来（离线） | 会退回宿主机 curl，只要 8090 端口在跑就算 PASS |
| M-2 宿主机也失败 | MCP server 没起 | `docker compose -f deploy/docker-compose.yml up -d`，或本机 `python mcp-server/server.py`（`MCP_TRANSPORT=streamable-http MCP_PORT=8090`） |
| M-3 HTTP 000 | 控制台没起 | 先起 Nexent 全栈（13 容器），再跑脚本 |
| M-3 三行缺失 | 回答没走 `agent/prompt.md` 的输出契约 | 检查智能体是否挂了 prompt 与 3 个 Skill；或把 `agent/sessions/real-w1-01.json` 里的示例回答格式对照一遍 |

## 4 与闸门的关系

- `acceptance.py --stage w2` 把 M-1..M-3 记为 MANUAL，不参与 PASS/FAIL，但周报与评审材料要贴证据。
- 三条证据齐了，W2 周报「三项 MANUAL」那一行才能从「未认领」改成 PASS。