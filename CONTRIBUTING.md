# 贡献指南

六个人、四周、一个交付仓。规则越少越好，但下面每一条都是踩过的坑。

## 1 五分钟上手

```bash
git clone <本仓地址>
python -m pip install -r requirements.txt -r requirements-dev.txt

python mcp-server/seed.py --reset     # 建种子库（可重复执行，--reset 清空重来）
python -m pytest tests -q             # 期望 17 passed, 1 skipped
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
| 功能 | `feat/agent-T{编号}-{简述}` | `feat/agent-T5-eval-metrics` |
| 修复 | `fix/agent-T{编号}-{简述}` | `fix/agent-T2-kg-2hop` |
| 文档 | `docs/agent-{简述}` | `docs/agent-judge-guide` |
| 工程 | `chore/agent-{简述}` | `chore/agent-ci-cache` |

- **不直接 push `main`**，一律 PR。
- 提交信息：`type(scope): 中文动宾`，一行说清改了什么。
  - scope 取值：`mcp` / `kg` / `onto` / `eval` / `skill` / `ui` / `ci` / `docs` / `data`
  - 例：`feat(mcp): 新增 std_align 的 fuzzy 匹配`
- 一次 PR 只做一件事；顺手改的格式化单独一个 PR。

## 3 合并门槛（CI 三绿 + 一张交接单）

1. **lint**：`ruff check .` 全过（规则只有 E/F/I，line-length 100）。
2. **test**：`python -m pytest tests -q` 全过；新增工具必须有测试。
3. **pipeline**：`python skeleton.py` 通、`python eval/run_eval.py` 六项不低于上一版、`python tools/check_evaluator.py` exit 0。
4. **交接单**：在 `docs/handoff/` 下补 `W{周}-T{编号}-{模块}.md`（模板见 `docs/handoff/TEMPLATE.md`），写清改了哪个契约、谁要跟着改、怎么验。

任何一项红了就别合，也别用 `--no-verify` 绕。

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

- `v0.1-internal`：W1 末，十工具 + 三 Skill 可跑（当前）。
- `v1.0-submit`：11-22 交付，打 tag 并附 `docs/judge-guide.md`。
