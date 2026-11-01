## 这个 PR 做了什么

<!-- 一句话说清；对应哪条赛题要求（R1–R5）也写上 -->

## 怎么验

```bash
# 贴能复现的命令与关键输出
```

## 影响面

- [ ] 改了 MCP 工具签名（已同步 `docs/mcp-contract.md`，已通知调用方）
- [ ] 改了本体 schema / 三元组（版本号 +1，旧快照保留）
- [ ] 改了评测集或指标口径（已在 PR 说明新旧分数对比）
- [ ] 只是文档 / 只加测试，不影响运行

## 自查

- [ ] `ruff check .` 通过
- [ ] `python -m pytest tests -q` 通过
- [ ] `python tools/selfcheck.py` 通过
- [ ] `python tools/acceptance.py --stage {当前周}` 无 FAIL
- [ ] 改动 ≤400 行，一次只做一件事
- [ ] 无真实患者数据、无密钥入库

## 评审

- [ ] 已 @ 一人 approve（T1 的 PR 由 T2 或 T3 批；GitHub 不算自己批自己）
- [ ] CI 三绿：`lint` / `test` / `pipeline`
- [ ] 合并方式 = Squash and merge，合并后删分支
