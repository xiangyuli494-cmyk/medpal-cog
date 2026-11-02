# 协作流程：分支 → PR → approve → 合并

> 2026-11-01 起强制。`main` 已开保护：**必须 PR，且至少 1 个 approve + CI 三绿**；非管理员直推会被拒，admin 阀门现状见 §4.1。
> 排期与任务见 [冲刺计划-1130.md](冲刺计划-1130.md) §9；任务卡见 [任务卡-三人版.md](任务卡-三人版.md)。

## 1 为什么这么做

三个人并行改一个仓，最贵的不是写代码，是互相覆盖：上一版是「谁先 push 谁赢」，结果是有人一觉醒来基线被打断。
分支 + 审批 + CI 闸，把冲突提前到 PR 里暴露，代价是每次多两次点击。

## 2 分支命名

| 类型 | 命名 | 例 |
| --- | --- | --- |
| 功能 | `feat/<模块>-<简述>` | `feat/kg-2hop`、`feat/onto-commit` |
| 修复 | `fix/<模块>-<简述>` | `fix/ingest-asset-id` |
| 文档 | `docs/<简述>` | `docs/git-flow` |
| 工程 | `chore/<简述>` | `chore/ci-cache` |

模块取值：`mcp` / `kg` / `onto` / `eval` / `skill` / `ui` / `ci` / `docs` / `data`。

## 3 一次完整的合并动线

```bash
# 0) 开工前同步，别在旧基线上写
git switch main && git pull --ff-only

# 1) 开分支（名字按 §2）
git switch -c feat/kg-2hop

# 2) 小步提交
git add -A
git commit -m "feat(kg): kg_query 支持两跳并返回路径锚点"

# 3) 本地过闸（CI 跑的是同样的东西）
python -m ruff check .
python -m pytest tests -q
python tools/acceptance.py --with-eval
python tools/selfcheck.py

# 4) 推分支并开 PR
git push -u origin feat/kg-2hop
# 网页：Compare & pull request → 填模板 → 提交

# 5) 找一个人 approve（T1 的 PR 只能由 T2/T3 批），CI 三绿后由 T1 合并
# 合并方式：Squash and merge；合并后删分支
```

## 4 保护规则现状（GitHub → Settings → Branches）

| 规则 | 值 | 说明 |
| --- | --- | --- |
| Require a pull request before merging | 开 | 非管理员直推 `main` 会被拒；T1 是 admin，见 §4.1 |
| Required approvals | **1** | 三个人足够轮转 |
| Dismiss stale approvals | 开 | 批完又推新提交 → 批准失效，重新批 |
| Require status checks | `lint` / `test` / `pipeline` | 三个 job 名来自 `.github/workflows/ci.yml` |
| Require conversation resolution | 开 | 评论没 resolve 合不了 |
| Allow force pushes / deletions | 关 | 历史只增 |
| Do not allow bypassing（`enforce_admins`） | **暂关**，T2/T3 加进来当天改**开** | 关着的时候 owner 直推 `main` 会成功（见 §4.1），等于规则对唯一 admin 不生效 |

### 4.1 实测：不设 `enforce_admins` 时到底拦住谁（2026-11-01）

在 PR #1 合并后做了对照实验：本地在 `main` 上打一个空提交再 `git push origin main`。

```text
remote: - Changes must be made through a pull request.
remote: - 3 of 3 required status checks are expected.
To https://github.com/.../medpal-cog.git
   eee60ac..15dd56a  main -> main          ← 推送成功
```

结论：**admin 直推是被放行的**，那两行只是警告。所以：

- 「不许直推」在 `enforce_admins=false` 下靠自觉，CI/approve 对 owner 完全不管用；
- 但**强推**是硬拦的（`allow_force_pushes=false` 对 admin 也生效），撤回那条空提交只能临时打开强推、推完立刻恢复；
- 想真正机械强制：等 T2/T3 账号进 Collaborator（能批 PR）当天执行 `ENFORCE_ADMINS=1 bash tools/gh-protect.sh`。在那之前保持 `false`，否则 T1 的 PR 没人能批、`main` 会冻住。

重新装一遍或换机器时执行（幂等）：

```bash
# 需要仓库 admin 权限的 token；本机已登录过 GitHub 可直接取
bash tools/gh-protect.sh
# 干跑看要改什么：
DRY_RUN=1 bash tools/gh-protect.sh
```

## 5 谁审谁

| PR 作者 | 必须由谁 approve | 谁来合并 |
| --- | --- | --- |
| T2 | T1 或 T3 | T1 |
| T3 | T1 或 T2 | T1 |
| T1（队长） | **T2 或 T3**（GitHub 不允许自己批自己） | T1 自己点合并 |

## 6 PR 要求

- ≤400 行；超过就拆。
- 标题同提交信息：`type(scope): 中文动宾`。
- 正文按 [PULL_REQUEST_TEMPLATE](../.github/PULL_REQUEST_TEMPLATE.md) 填：做了什么 / 怎么验 / 影响面 / 自查。
- 贴证据：命令 + 关键输出，或截图路径；不要只写「已测试」。
- 改契约（工具签名 / 本体 schema / 评测口径）必须先改文档，再改实现，并在 PR 里 @ 相关人。

## 7 合并之后

- 勾选 Delete branch（GitHub 默认）。
- 每周日闸门后 T1 打轻量 tag：`git tag w1 && git push origin w1`（便于回溯本周状态）。
- 交付打 `v1.0`：`git tag -a v1.0 -m "11-30 交付" && git push origin v1.0`。

## 8 常见卡点

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 推 `main` 报 `protected branch hook declined` | 保护生效 | 改推分支，开 PR |
| PR 一直显示 `Expected — Waiting for status to be reported` | check 名不对（改名了） | 按 `ci.yml` 里 job 的 `name:` 改保护配置，重跑 `tools/gh-protect.sh` |
| 点了 approve 但还是合不了 | 之后又推了提交（stale 批准失效） | 重新 approve |
| 合不了，提示 review required | 作者自己批了自己（GitHub 不计） | 找另一人批 |
| CI 挂了但本地绿 | 本机 Python 3.12 vs CI 同版本；多为缺依赖或路径大小写 | 看 job 日志；`python -m pip install -r requirements.txt -r requirements-dev.txt` |