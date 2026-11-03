# 贡献指南

三个人、四周、一个交付仓。规则越少越好，但下面每一条都是踩过的坑。

> 排期见 [docs/冲刺计划-1130.md](docs/冲刺计划-1130.md)，分工见 [docs/任务卡-三人版.md](docs/任务卡-三人版.md)。
> 分支怎么开、PR 怎么批：[docs/git-flow.md](docs/git-flow.md)。

## 1 五分钟上手

```bash
git clone <本仓地址>
python -m pip install -r requirements.txt -r requirements-dev.txt

python mcp-server/seed.py --reset     # 建种子库（可重复执行，--reset 清空重来）
python -m pytest tests -q             # 期望 43 passed（未装 PyMuPDF 时 1 skipped）
python tools/selfcheck.py             # 一键自检，绿了再开工
```

Windows 必设（否则终端乱码 / 回环请求被代理拦）：

```bat
set PYTHONIOENCODING=utf-8
set NO_PROXY=127.0.0.1,localhost
```

## 2 分支与提交

| 类型 | 命名 | 例 |
| --- | --- | --- |
| 功能 | `feat/{模块}-{简述}` | `feat/kg-2hop`、`feat/onto-commit` |
| 修复 | `fix/{模块}-{简述}` | `fix/ingest-asset-id` |
| 文档 | `docs/{简述}` | `docs/git-flow` |
| 工程 | `chore/{简述}` | `chore/ci-cache` |

- **不直接 push `main`**：保护已开且 `enforce_admins=true`（2026-11-02 起），**管理员也推不进去**，一律走分支 + PR。
- 流程：开分支 → push → 开 PR → **至少 1 个 approve** → CI 三绿 → **T1（队长）点合并**。
- **T1 自己开的 PR 必须由 T2 或 T3 approve**（GitHub 不计给自己批的票）。
- 批完又推了新提交，旧批准自动失效（dismiss stale reviews），需要重新批。
- 提交信息：`type(scope): 中文动宾`，一行说清改了什么。
  - scope 取值：`mcp` / `kg` / `onto` / `eval` / `skill` / `ui` / `ci` / `docs` / `data`
  - 例：`feat(mcp): 新增 std_align 的 fuzzy 匹配`
- 一次 PR 只做一件事；顺手改的格式化单独一个 PR。

## 3 合并门槛（CI 三绿 + acceptance + 一张 approve）

1. **lint**：`ruff check .` 全过（规则只有 E/F/I，line-length 100）。
2. **test**：`python -m pytest tests -q` 全过；新增工具必须有测试。
3. **pipeline**：`python skeleton.py` 通、`python eval/run_eval.py` 六项不低于上一版、`python tools/check_evaluator.py` exit 0。
4. **验收**：`python tools/acceptance.py --stage {当前周}` 无 FAIL（阈值见 [冲刺计划 §10](docs/冲刺计划-1130.md)）。
5. **一张 approve**：由 T1/T2/T3 中非作者的人批（T1 的 PR 由 T2 或 T3 批）。

以上五条是硬门槛。**交接单不进门槛**：`docs/handoff/W{周}-{代号}-{模块}.md`（模板见 `docs/handoff/TEMPLATE.md`）写清改了哪个契约、谁要跟着改、怎么验，周日闸门核对证据位时才要求有。

任何一项红了就别合，也别用 `--no-verify` 绕。分支保护卡的是 `ci.yml` 里三个 job 的 **name**：`lint (ruff)` / `test (pytest)` / `pipeline (skeleton + eval)`（改名要同步跑 `tools/gh-protect.sh`）。

## 4 代码规范

- Python 3.12，标准库优先；新增第三方依赖要走 PR 说明理由，并写进 `requirements.txt`。
- 工具函数签名一旦对外（写进 `skills/`、`docs/mcp-contract.md`、Nexent 配置），**改签名等于破坏契约**：先改契约文档，再改实现，再通知全组。
- 所有 MCP 工具返回 `{"ok": bool, ...}`；失败必须带 `reason` 与 `hint`，不许 `except: pass`。
- 路径一律用 `Path(__file__).resolve()` 推导，不写死绝对路径。
- 中文注释、中文报错信息；标识符、日志字段保持英文。
- 不留 `print` 调试残留；临时脚本放 `tmp/`（已 gitignore）。

## 5 数据与合规（红线）

- 只提交**公开标准数据**与**合成数据**。真实患者信息、真实身份证号/手机号、医院单据原图，一律不进仓库。
- 新增样本必须带标注：`synthetic`（自己造的）或 `public`（公开来源 + 链接 + 版本）。
- 不提交任何 API Key；本地用 `.env`（已 gitignore），模板见 `.env.example`。

## 6 谁能改哪

见 `CODEOWNERS`。改别人的地盘先在该 PR 里 @ 对方，别等合并时才发现。

## 7 发版

- `v0.1-internal`：W1 末（11-08），十工具 + 三 Skill 可跑（当前基线）。
- 每周闸门后 T1 打轻量 tag `w1`/`w2`/`w3`，便于回溯。
- `v1.0`：**11-30** 交付，`git tag -a v1.0 -m "11-30 交付"` + `git push origin v1.0`，附 `docs/judge-guide.md`。
