# 文档地图

按「我要干什么」找，不按目录结构找。

| 我要… | 看 |
| --- | --- |
| 弄懂这题到底要做什么 | [赛题3-方案-v1.2.md](赛题3-方案-v1.2.md)（747 行，全组唯一口径） |
| 调工具 / 加工具 | [mcp-contract.md](mcp-contract.md) |
| 改本体 / 加三元组 | [ontology-schema.md](ontology-schema.md) |
| 改决策链结构 | [trace-schema.md](trace-schema.md) |
| 知道自己这周干什么 | [W1-角色任务卡.md](W1-角色任务卡.md) |
| 提交前自查 | [rules.md](rules.md) |
| 评审怎么讲 | [judge-guide.md](judge-guide.md) |
| 交接给下一个人 | [handoff/TEMPLATE.md](handoff/TEMPLATE.md) |
| 这个仓怎么来的 | [adr/ADR-001-仓库拆分与历史迁移.md](adr/ADR-001-仓库拆分与历史迁移.md)、[migration.md](migration.md) |

## 目录约定

- 方案、契约、schema、规则：直接放 `docs/` 根，文件名即主题。
- 决策记录：`docs/adr/`，一个决策一个文件，编号递增，**只增不改**（改了写新 ADR 并标注取代关系）。
- 交接单：`docs/handoff/`，命名 `W{周}-T{编号}-{模块}.md`。
- 一次性分析、草稿：不进仓，放 `tmp/`（已 gitignore）。

## 写文档的三条硬规矩

1. **数字必须能被命令复现**。写「17 三元组」，旁边就得有 `python mcp-server/seed.py --reset`。
2. **不写没跑通的东西**。计划中的能力写在「待办」，不要混进「已完成」。
3. **改了实现当天改文档**。文档过期比没文档更贵。
