# 主智能体配置（v0）

把「门诊主诉 → 跨文档取证 → 科室与检查建议」接进 Nexent 需要的四样东西都在这个目录：
提示词、工具白名单、会话样例、接线步骤。**这里只有配置，没有实测结论** ——
平台侧真实表现请回填到 `agent/sessions/real-*.json`（见 §6），在此之前不许在文档里写「已实测」。

| 文件 | 作用 |
| --- | --- |
| `prompt.md` | 系统提示词，整段粘贴进 Nexent 的智能体配置 |
| `config.json` | 机器可读配置：MCP 地址、10 个工具白名单、3 个 Skill、三行输出契约、护栏 |
| `sessions/s-01..03.json` | 三份会话样例（常态 / 报警 / 冲突），由离线规则引擎回放生成，用于对齐工具调用形状与输出格式 |
| `../tests/test_agent_config.py` | 校验配置自洽：白名单 = MCP 实际注册的 10 个工具、Skill 目录存在、样例符合输出契约 |

## 1 前置：MCP 服务已在跑

```bash
# 交付形态：streamable-http，端口与平台端口表错开（E-7 里 8090 是我们固定的）
MCP_TRANSPORT=streamable-http MCP_PORT=8090 python mcp-server/server.py
```

探活（能在容器里跑就在容器里跑，因为 Nexent 的容器要用 `host.docker.internal` 回连宿主机）：

```bash
curl -s -X POST http://host.docker.internal:8090/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
# 期望：serverInfo.name = medpal-cog
```

## 2 在 Nexent 里建智能体

1. 打开控制台 `http://localhost:3000`（v2.7.0 实测端口，见 `docs/env.md`）。
2. 智能体 → 新建 → 名称填 `medpal-cog`。
3. 系统提示词：整段粘贴 `agent/prompt.md`。
4. 工具：先接 MCP（下一个 §），勾选 `config.json` 里 `tools.mcp` 的 10 个；
   平台自带的 `search-knowledge-base` / `analyze-image` 若当前部署没开，跳过即可，
   提示词里已经写了「未启用就跳过」。
5. 挂 Skill：三个目录一起挂上 —— `skills/s1-asset-audit`、`s2-ontology-evolve`、`s3-evidence-decision`。
6. 模型参数：温度偏低（0.2 左右），`max_rounds=4` 由提示词约束，不靠平台默认。

界面按钮文案随版本变，**以 `docs/env.md` §2.5 的实测记录为准**，本节只给顺序。

## 3 接 MCP（远程，v2.7.0 的坑在这）

- 传输：`streamable-http`；URL：`http://host.docker.internal:8090/mcp`。
- 平台是 docker compose 起的（`-p nexent`，13 个容器），容器里 `127.0.0.1` 指它自己，
  所以要写 `host.docker.internal`；同机 Linux 原生部署才写 `127.0.0.1`。
- 工具列表刷新后应看到 10 个：`ingest_asset / get_asset_card / kg_query / onto_propose /
  onto_commit / std_align / trace_write / skill_export / kb_search / health`。
  少一个就说明 `mcp-server/server.py` 的 `@mcp.tool()` 被条件导入挡了，先跑 `python tools/acceptance.py` 看 A-03。

## 4 输出契约（三行，评测和人工验收都按这个抓）

```
科室：消化内科
检查项：幽门螺杆菌呼气试验、胃镜
完整率：1.00
```

- 顺序固定、全角冒号、多个检查项用顿号。
- 冲突单独一行放三行**之前**：`冲突：布洛芬（NSAIDs）与消化性溃疡存在禁忌关系`。
- `完整率` 取 `trace_write` 的 `completeness`（两位小数）；没调通写 `完整率：未取到`，不许编。

平台评估器算不出溯源完整率（E-5），所以这一行只能由智能体自己带出来。

## 5 三份样例怎么用

`sessions/s-01.json` 常态、`s-02.json` 报警、`s-03.json` 冲突。每份含：提问、期望的工具调用形状、
证据锚点列表、期望三行尾。在平台上按同一提问回放，比对 `expected_tail` 即可，不需要人工判分。

```bash
python -m pytest tests/test_agent_config.py -q     # 配置自洽 + 样例符合契约
```

## 6 回填实测（W1 闸门要的那份「一次会话 json」）

在平台跑通一次后，把会话导出成 `agent/sessions/real-w1-01.json`，至少包含：

```json
{
  "source": "nexent v2.7.0 实跑，2026-11-0X，控制台 http://localhost:3000",
  "question": "……",
  "tool_calls": [{"tool": "kb_search", "ok": true}],
  "answer_tail": ["科室：…", "检查项：…", "完整率：1.00"],
  "screenshot": "docs/assets/w1-session.png"
}
```

没有这份文件，R5「Nexent 可运行」只能写「配置就绪、未实测」。

## 7 故障对照

| 现象 | 先查 |
| --- | --- |
| 工具列表空 / 0 个 | MCP 是否 `streamable-http` 起在 8090；容器内能否 `curl host.docker.internal:8090` |
| 只有 9 个工具 | `python tools/acceptance.py` 的 A-03 会说缺哪个 |
| 回答了但没有三行尾 | 提示词没粘全，重点看「输出格式（必须遵守）」那段 |
| 完整率一直是 `未取到` | `trace_write` 调用失败，先 `health`，再看 `reports/` 有没有新报告 |
| 报警病例没给内镜 | 提示词「报警优先（硬规则）」被模型忽略，降低温度或把该段提到最前 |

## 8 边界

不给药品剂量、不给处方、不下确定性诊断；证据不足时输出缺口清单而不是结论。
这三条同时写在提示词「禁止」段与 `config.json` 的 `guardrails`，两处都要过测试。
