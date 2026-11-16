# W3-T1 PR 审核与联调

> 负责人：T1 / @xiangyuli494-cmyk；日期：2026-11-16。
> 主分支基线 `94a5e76`；本记录覆盖审核、v1 配置准备与运行取证，不替代冲刺计划。

## 1 已完成的审核

| PR / 精确 head | 已复核 | 结论与评论 |
| --- | --- | --- |
| #31 / `bab6ca4` | 提案、提交、回滚相关 16 条测试通过；独立临时库复现两处缺陷 | [请求修改](https://github.com/xiangyuli494-cmyk/medpal-cog/pull/31#pullrequestreview-5922370530) |
| #35 / `21f52c9` | ruff 通过；81 passed / 4 skipped；前 24 条逐字节不变；30/20 题表面分数全 1.000 | [请求修改](https://github.com/xiangyuli494-cmyk/medpal-cog/pull/35#pullrequestreview-5922399444) |
| #36 / `f4a6cdd` | 远端 Docker 构建与探活 CI success；本机 ruff 通过；复现启动重灌破坏持久化 | [请求修改](https://github.com/xiangyuli494-cmyk/medpal-cog/pull/36#pullrequestreview-5922412906) |

- #31：同义冲突提交后旧检查边被删而规范边未补，活跃检查边为零；
  回滚 v1.1→v1.0 后仍保留 v1.1 的置信度和证据来源。
- #35：`score_one(row["gold"], got)` 未传入顶层 `gold_evidence`，
  空证据返回也得 1.0。显式传入新题金标准后，Q025/Q026/Q027/Q029/Q030
  的命中率分别为 0、0、0.5、0.5、0.5。
  Q030 的两条锚点属于同一资产；默认两跳调用没有验证 `hops=3` 标签。
- #36：已有库发布为 v1.0、加入运行时上传资产后，执行入口中的 ingest 命令，
  当前版本变为 v0.9、上传资产消失。需限制首次初始化并验证重启持久化。
  它还包含 #35 的评测文件，不能绕过 #35 的修改请求直接合并。

三个 PR 均有实际缺陷，本轮未批准或合并。修复后按新 head 重新验；
不能只沿用旧提交的 CI。#32 是 T1 自己的 PR，仍需要 T2/T3 有效批准。

## 2 T1 配置与证据

`agent/config.json` 升为 v1，最多三跳；提示词新增 S1/S2/S3 选择与执行证据、
发布前确认、相邻步跨资产检查，以及证据不足时的退回规则。
配置与提示词不改变 10 个工具名和三行输出契约，也不代表平台已运行。

宿主机 streamable-http 实测：精确列出 10 个工具；`health` 返回 ok=true、
37 条三元组、70 资产、v0.9；`tests/test_http_client.py` 返回 HTTP TRANSPORT OK。
[HTTP 证据](evidence/W3-T1-host-http-2026-11-16.json) 只证明宿主机传输可用。

[图路径检查](evidence/W3-T1-path-audit-2026-11-16.json)：37 条活跃边上，
相邻边来自不同资产的两跳路径有 2 个方向，三跳为 0。
两跳例为 I10→肾功能←N20，只说明共享检查项，不能推断疾病之间的临床关系。
本周“两跳 ≥3 题、三跳 ≥1 题”的业务验收仍未完成。

## 3 环境恢复后执行

当前 Windows HypervisorPresent=False，Docker daemon 不可用，控制台 :3000 拒绝连接。
交接记录显示已设 hypervisorlaunchtype=auto、尚需重启；本会话没有重启电脑。
本次读取 BCD 配置被权限拒绝，未修改启动配置。

1. 保存工作并重启后验证 `HypervisorPresent`，启动 Docker Desktop 与既有 Nexent。
2. 验 M-1：`docker ps --format "{{.Names}} {{.Status}}"`，≥13 个目标容器运行。
3. 验 M-2：从 Nexent 运行容器请求 MCP initialize，核对 JSON-RPC result 中
   `serverInfo.name=medpal-cog`；宿主机成功不能抵消容器失败。
4. 验 M-3：控制台工具恰为 10 个；保存工具列表截图及真实回答原文，校验三行顺序与值。
5. 按 `agent/README.md` 更新主智能体提示词并挂载三个 Skill。
   对常态、报警、冲突各执行一次；至少一份会话有真实 Skill 事件且其结果进入最终回答。
6. 在 #31 缺陷修复、版本化验收后，执行 v0.9→v1.0 同题前后对比。
   需用户确认的发布通过确认流程执行，不把脚本回放写成实跑。
7. 与 T2/T3 补齐业务多跳样本，逐步验资产锚点，再做 v1.0→v1.1 演示。

真实会话保存到 `agent/sessions/real-w3-*.json`，包含原始平台记录位置、时间、
模型、conversation_id、Skill 事件、工具参数/结果、trace_id 与三行回答。
进化对比同时保存前后版本及新三元组 ID。没有这些原始证据就保留“未验收”。

## 4 验证与责任

```bash
python -m ruff check .
python -m pytest tests
python tools/check_evaluator.py
python tools/acceptance.py --stage w3 --with-eval
```

本分支 ruff 与契约通过、pytest 85 passed；W3 验收 PASS 22 / FAIL 3 / MANUAL 3，
失败为 A-07、A-09、A-14。验收会重建数据，只在独立审核目录执行。当前周仍有未完成项，
非零退出不得改成通过；评测证据缺陷修好后重新报告指标。

T2 修 #31 的本体/回滚问题并补到 ≥50；T3 修 #35/#36 的评测与持久化；
T1 复审、合并符合条件的 PR，完成平台联调和真实会话取证。
