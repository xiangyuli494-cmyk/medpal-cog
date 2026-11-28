# T1 审核与联调执行单（11/28 状态补正）

> 当前main为`f5aed6b`。#37审核修订基线`f106693`已同步main并推送；本次补正文档当前态，最新head以PR页面为准。
> 本页区分已执行、待审核与待演示，完整周报见 [W3 周报](W3-周报-2026-11-22.md)。

## 已执行与可核对的证据

- 11/17 已验证 Hypervisor=True、14 个相关容器运行、Nexent HTTP 200、容器内 MCP initialize 成功；不需再重启。
- 三个 Skill 已上传挂载，agent_id=2 工具白名单恰为十个，v1 提示词已应用。
- 11/18 模型连通后完成常态、报警、冲突三次实际问答。会话摘要位于 `agent/sessions/real-w3-*.json`。
- 完整的已发布执行证据为 `agent/deliverables/w3/nexent/*-actions.json`，包含 parse 代码和 execution_logs 返回；
  session 中的 `mcp_execution_index` 以零起始数组索引定位每次调用代码和返回，代码行号从一开始。
- `tool_calls` 是精简摘要，只保留 trace_write；完整 MCP 调用以执行索引为准。三份会话分别索引 10、9、8 次 MCP 调用。
- 三次以 `POST /agent/run`、`is_debug=true` 运行，平台事件未返回持久化 conversation_id。
  此字段明确为 null，并保留 debug_run_workspace_id、trace_id 和执行日志 SHA-256；不把运行目录标识冒充对话 ID。

原始 trace 来自 `store.get_trace`。展示 trace 增加 schema、trace_completeness、unresolved、sources，
其来源与取值已逐项记录在 `*-conversion.json:added_fields`。
完整率与 unresolved 对照实际 trace_write 返回值；sources 使用导出时的 evidence 与数据库三元组来源反推。
原始 op/ref 的结构适配在 changes 中记录，不改原始数据库，也不虚构 conclude 步。
最终回答在 session.actual_answer 和 actions.final_answer；原始五步/四步 trace 没有 conclude 的限制继续保留。
完整率 1.00 不说明检索或术语对齐没有业务缺口，也不说明建议已经获得临床验证。

## 队友 PR 复核（11/28 状态补正）

| PR/head | 结果 | 尚需处理 |
| --- | --- | --- |
| #31 / `777ccd2` | 两处原 P1 复现通过；128 passed，ruff 通过；T3 已批准 | W3 带评测验收 PASS 22 / FAIL 3 / MANUAL 3，失败 A-07/B-05/B-08；未合并 |
| #38 / `22d676c` | 锚点清单、估算假设已修正；T2 已批准当前提交 | T1已Approve并关闭两条已修讨论；周验收失败仍如实保留 |
| #39 / `a0350f2` | W4 封版文档草稿 | 安装命令漏开发依赖；扫描要求为空会匹配文档自身；问题已评论并给出具体改法，等待T3修订 |

前轮 #35/#36 的证据评分和持久化缺陷已经修正并合入 main，不能继续写成「尚未修复/未合并」。

## T1 修订状态与待执行

1. #32九项正式审核意见已修复并推送`395737c`，T3已Approve；等待T2复审更新旧修改请求。
2. #37会话索引与转换来源已随`f106693`推送；11/28按T3新意见补正文档，并在标题/描述标明评审型，待队友复审。
3. 本地分支已同步 main，复测结果写入 W4 执行单；保留旧原始取证文件与其当时基线，不用新版本覆盖旧会话版本。
4. 在审核后的隔离演示库复验跨文档两跳至少三题、三跳至少一题；每步核对连续路径、真实锚点与相邻资产不同。
5. 完成同题 v0.9→v1.0→v1.1 两次差分、对应回答变化和三段录屏；本轮回滚单测不充作平台进化演示。
6. 11/28本地已准备PPT审阅版、五分钟脚本和十问，未加入本PR；两次真人演练、三轮真实版本演示及最终tag仍未完成。11/24三次基线问答不替代版本演示。

## 验证口径

11/18 T1 原分支本机为 94 passed；队友机器为 90 passed / 4 skipped，取决于 PDF 依赖。
前者是当时本机实测，后者是队友环境实测，不把任一口径冒充当前全平台统一值。
本轮修改后测试结果另行记录，不沿用历史计数。

11/18 原分支 `acceptance --stage w3 --no-seed` 为结构检查 PASS 13 / FAIL 3 / MANUAL 3，未带评测。
11/19 当前 main 同代码基线带评测检查 PASS 21 / FAIL 4 / MANUAL 3。
11/23 #31 隔离副本带评测检查 PASS 22 / FAIL 3 / MANUAL 3。
各次命令、分支与日期不可混用；运行会重建数据库的命令只在隔离副本执行。
