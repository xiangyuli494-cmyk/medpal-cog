# medpal-cog 工程规则（赛题3）

> 版本 **v2.0** · 2026-11-01 · 三人制（T1 队长 / T2 / T3）
> 适用范围：本仓库全部跟踪文件（`mcp-server/`、`ontology/`、`parse/`、`skills/`、`eval/`、`data/`、`web/`、`tools/`、`docs/`）。
> 本文件 v1.0（2026-10-22，六人制、仓内 `agent/` 前缀）**已废止**；分支与合并的权威来源是 [`docs/git-flow.md`](git-flow.md) 与 [`CONTRIBUTING.md`](../CONTRIBUTING.md)，排期的权威来源是 [`docs/冲刺计划-1130.md`](冲刺计划-1130.md)。

---

## 1. 分支

| 类型 | 命名 | 例 |
| --- | --- | --- |
| 功能 | `feat/{模块}-{简述}` | `feat/kg-2hop` |
| 修复 | `fix/{模块}-{简述}` | `fix/mcp-health-timeout` |
| 文档 | `docs/{简述}` | `docs/git-flow` |
| 工程 | `chore/{简述}` | `chore/ci-cache` |

- 模块取值：`mcp` / `kg` / `onto` / `eval` / `skill` / `ui` / `ci` / `docs` / `data`
- 从最新 `main` 切出，存活 ≤ 7 天；每周至少 `git pull --rebase origin main` 一次
- 一个 PR 只做一件事、只动一层

## 2. 提交信息

```
<type>(<scope>): <描述>
```

- type ∈ `feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert`
- scope = §1 的模块取值
- 描述用中文、动宾、不超过 50 字、不加句号

## 3. PR 与合并

合并门槛 = CI 三道 check 全绿 + `acceptance.py --stage {当前周}` 无 FAIL + 一张非作者 approve：

1. `lint (ruff)` job 绿
2. `test (pytest)` job 绿
3. `pipeline (skeleton + eval)` job 绿
4. 非作者 approve ≥1（T1 的 PR 由 T2 或 T3 批）

岗位职能见 [`CODEOWNERS`](../CODEOWNERS)。**交接单不进合并门槛**，只在周日闸门核对证据位时要求有（见 `docs/handoff/TEMPLATE.md`）。

## 4. 交接单

文件名 `W{周}-{代号}-{模块}.md`，例 `W1-T1-nexent-mcp-接入.md`；模板 `docs/handoff/TEMPLATE.md`。四节：干了什么 / 数据流 / 改了什么 / 怎么验证。

## 5. 骨架纪律（红线）

1. **一次只加粗一根骨头。** 一个 PR 只改一层，跨层拆 PR。
2. **先红再绿。** 动骨架前先写一个会失败的测试或评测条目，PR 里贴红灯。
3. **骨架命令坏了，全组停手。** `python -B skeleton.py` 不绿期间，只允许修它。

> 为什么加 `-B`：改一个数字但文件长度不变时，`__pycache__` 会让门禁**假绿**。已实测过 0.80→0.81 未触发变红。

## 6. Definition of Done

- [ ] 代码在本仓库对应目录下，没有新增第三方依赖（除已在 `requirements.txt`）
- [ ] 有单元测试，`python -m pytest tests` 全绿
- [ ] `python -B skeleton.py` 仍绿；`python tools/acceptance.py --stage {当前周}` 无 FAIL
- [ ] 交接单已提交（周闸门要查）
- [ ] 验收标准逐条自测过，附输出
- [ ] 没有 committed 的 Key、数据库、PDF、音视频

## 7. 不许做

- 直接向 `main` 推送（含强推）
- 修改别人的模块文件（`mcp-server/`、`ontology/`、`parse/` 等按 `CODEOWNERS` 划分）
- 在 PR 里顺手重构无关代码
- 用 AI 生成后直接提交且不说明（交接单「人工修改点」必填）
