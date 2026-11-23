# T1 W3 审核包

本包提交至 T1 的 PR #37，供 T2/T3 审核；不代表整周验收完成。
没有修改 T2 本体实现、T3 数据集/Skill 包/前端或部署代码。

| 文件 | 状态与来源 |
| --- | --- |
| `report.html` | 已生成的独立 HTML，复用现有查看器；包含实际 MCP HTTP trace，非 Nexent |
| `trace.json` | trace_write 生成、读取实际数据库记录，schema 校验通过 |
| `SKILL.md` | 由这条 trace 的实际 skill_export 返回，草稿未安装 |
| `tool-evidence.json` | health/std_align/kg_query/trace_write/skill_export 的实际调用与结果 |
| `broken-report.html` | 既有断链夹具的自包含报告，不能作为成功推理证据 |
| `path-audit.json` | 四道业务题的只读图预检；当前四题均 BLOCKED |

本次正常报告完整率 1.00、unresolved 为空，但引用均来自同一资产，
因此只作为报告导出和模板导出的功能验收，不用于跨文档三跳验收。
浏览器工具禁止打开 file 协议，本次未绕过限制；请本地双击检查页面外观和断链红标。

题目和逐字演示稿在 `agent/validation/`；它们是 T1 定题与执行稿，未改 T3 的评测集。
模型连接现已测通，三个真实平台会话已保存至 `agent/sessions/real-w3-*.json`。
`nexent/` 下有常态、报警、冲突的实际执行记录、原始 trace、展示适配 trace 及报告。
原始 trace 存在操作名/ref 与前端 schema 不一致的问题；转换清单逐项保留，不改写数据库原始记录。
本体跨文档路径仍未满足，两次进化差分和三段录屏尚未完成，等待审核后本体输入。
完整率只代表引用可解析，不代表临床正确性。

历史验证（11/18 本机，已装 PDF 依赖）：ruff 通过；pytest 94 passed。
队友环境为 90 passed / 4 skipped，分别注明环境，不把收集数作为通过数。
展示适配 trace 的 schema 校验通过。

11/23 本地审核修订：session 是摘要，`mcp_execution_index` 可按事件索引定位
`*-actions.json` 中每次 MCP 调用的代码和真实返回；trace_write 返回单独定位并比对。
debug API 没返回 conversation_id，已明确记 null 并保留运行目录标识，未编造对话 ID。
转换清单新增 `added_fields`，逐项交代 schema/完整率/unresolved/sources 的来源。
原始 trace 没有 conclude 步，最终回答保留在 session.actual_answer 与 actions.final_answer。
独立报告各自带数据，也保留上传其他 JSON 的查看器功能；页面外观尚待人工核对。
