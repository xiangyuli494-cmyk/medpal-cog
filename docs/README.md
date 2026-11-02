# 文档地图

按「我要干什么」找，不按目录结构找。

| 我要… | 看 |
| --- | --- |
| 弄懂这题到底要做什么 | [赛题3-方案-v1.2.md](赛题3-方案-v1.2.md)（747 行，**历史快照**：只读技术判断；排期与阈值以冲刺计划为准） |
| 开工第一天照着做 | [开工检查单.md](开工检查单.md)（克隆→跑绿→认领任务→提 PR，30 分钟） |
| 环境怎么搭、起不来怎么查 | [env.md](env.md)（v2.7.0 实测：冷启 61 秒 / 13 容器 / 端口表） |
| 调工具 / 加工具 | [mcp-contract.md](mcp-contract.md) |
| 改本体 / 加三元组 | [ontology-schema.md](ontology-schema.md) |
| 改决策链结构 | [trace-schema.md](trace-schema.md) |
| 知道这周干什么、几号交 | [冲刺计划-1130.md](冲刺计划-1130.md)（总排期 + 闸门 + 风险） |
| 一项算不算做完 | [冲刺计划-1130.md §10](冲刺计划-1130.md)：16 项结构 + 7 项指标，`python tools/acceptance.py --with-eval` |
| 开分支、请人 approve、合并卡住了 | [git-flow.md](git-flow.md)（保护规则 + 谁审谁 + 常见卡点） |
| 知道自己那几项怎么算过 | [任务卡-三人版.md](任务卡-三人版.md) |
| 提交前自查 | [rules.md](rules.md) |
| 评审怎么讲 | [judge-guide.md](judge-guide.md) |
| 交接给下一个人 | [handoff/TEMPLATE.md](handoff/TEMPLATE.md) |
| 这个仓怎么来的 | [adr/ADR-001-仓库拆分与历史迁移.md](adr/ADR-001-仓库拆分与历史迁移.md)、[migration.md](migration.md)（含第二批：旧仓未合并分支怎么搬的） |
| 为什么这么排、为什么不回旧仓 | [adr/ADR-002-对齐旧仓与分支保护.md](adr/ADR-002-对齐旧仓与分支保护.md) |
| 主智能体怎么接进 Nexent | [../agent/README.md](../agent/README.md)（提示词、工具白名单、3 份会话样例、故障表） |

## 目录约定

- 方案、契约、schema、规则：直接放 `docs/` 根，文件名即主题。
- 决策记录：`docs/adr/`，一个决策一个文件，编号递增，**只增不改**（改了写新 ADR 并标注取代关系）。
- 交接单：`docs/handoff/`，命名 `W{周}-T{编号}-{模块}.md`。
- 一次性分析、草稿：不进仓，放 `tmp/`（已 gitignore）。
- 排期与任务卡：`docs/冲刺计划-1130.md`（权威）、`docs/任务卡-三人版.md`；旧六人任务卡保留但标停用。

## 写文档的三条硬规矩

1. **数字必须能被命令复现**。写「37 三元组」，旁边就得有 `python mcp-server/seed.py --reset && python tools/ingest_all.py`。
2. **不写没跑通的东西**。计划中的能力写在「待办」，不要混进「已完成」。
3. **改了实现当天改文档**。文档过期比没文档更贵。
