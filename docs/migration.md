# 迁移记录：从 `medpal` 到 `medpal-cog`

这份文档回答三个问题：**搬了什么、怎么搬的、搬完怎么验**。评审问「历史还在吗」时直接给这个文件。

## 1 边界

| | 旧仓 `medpal` | 新仓 `medpal-cog` |
| --- | --- | --- |
| 内容 | 院内智慧陪诊终端（已冻结）+ 历史遗留 | 赛题3 可进化决策智能体 |
| 状态 | **只读归档**，不再接收赛题3提交 | 唯一活跃交付仓 |
| 分支 | `main` + 33 个历史分支 + tag `w1-freeze-20261022` | `main` + 功能分支 |
| CI | 四条 workflow 仍指向陪诊线路径 | 三条 job：lint / test / pipeline |

## 2 搬了什么

- **代码与文档**：`agent/` 下全部内容，展平到新仓根。
- **提交历史**：`git subtree split` 抽出的 10 个提交，作者、时间、提交信息原样保留。
- **数据资产**：61 张 Asset Card、三类模态样本各 20 份、`eval/dataset/v0.jsonl` 20 条（迁入时 14 条，W1 补齐报警/俗称/病程 6 条）。
- **没搬**：陪诊线的 `backend/`、`demo/`、`docs/plan`、`docs/specs`、冻结说明 `FROZEN.md`——它们留在旧仓。

## 3 怎么搬的（可复现）

在旧仓执行，抽出只含 `agent/` 的历史：

```bash
cd /e/deepseek-data/medpal
git subtree split -P agent -b cog-main origin/main
# 产出 10 个提交，tip = 9ad29eb23888a9750f22f7e01495dcd944ae3f45
```

建新仓并导入：

```bash
mkdir -p /e/deepseek-data/medpal-cog && cd /e/deepseek-data/medpal-cog
git init -b main
git fetch /e/deepseek-data/medpal cog-main
git reset --hard FETCH_HEAD
git remote remove origin 2>/dev/null || true
```

展平路径前缀（`git subtree split` 已把 `agent/` 去掉，剩下的是文本里的引用）：

```bash
# 17 个 .md/.py 里 158 处 agent/ 前缀
git grep -l "agent/" | xargs sed -i 's#agent/##g'
# 模块式引用改脚本式调用
sed -i 's#python -m agent.skeleton#python skeleton.py#g; s#python -m agent.ontology#python -m ontology#g' $(git grep -l "agent\." || true)
```

修掉展平后失效的相对路径：

| 文件 | 改动 |
| --- | --- |
| `skeleton.py` | `Path(__file__).resolve().parent.parent` → `.parent`；docstring 同步 |
| `tests/test_trace_schema.py` | `AGENT.parent / "tmp"` → `AGENT / "tmp"` |
| `tools/check_evaluator.py` | `ROOT = parents[2]` → `parents[1]`，`EVALUATOR` 指向 `eval/` |
| `tools/probe_llm.py` | 用法串去掉 `-m agent.tools` |
| `__init__.py`（根） | 删除：拆出来的仓不再是 Python 包 |

提交历史与哈希的对应关系保留在旧仓：`git log cog-main` 仍能查到切分点。

## 4 搬完怎么验（一条命令 + 四条手工）

```bash
python tools/selfcheck.py        # 全绿即通过
```

手工四项：

1. `python mcp-server/seed.py --reset` → 输出 17 三元组 / 15 锚点；再 `python tools/ingest_all.py` → 61 张卡 + 37 三元组 / 43 锚点；
2. `python -m pytest tests -q` → 43 passed（未装 PyMuPDF 时 1 skipped）；
3. `python eval/run_eval.py` → 六项 100%；
4. `python skeleton.py` → `OK 5 steps | 科室=消化内科 | 溯源完整率=0.75`。

## 5 旧仓收尾清单（T1 执行一次即可）

```bash
cd /e/deepseek-data/medpal
git checkout main

# 1) 根 README 顶部加一行指向新仓
#    在标题下插入：> 赛题3 已迁至 medpal-cog，本仓仅保留陪诊线（2026-10-22 冻结）。

# 2) 给 agent/ 加退役说明（保留文件，避免老链接 404）
cat > agent/README.md <<'EOT'
> **本目录已迁移**
> 赛题3「可进化决策智能体」迁至 medpal-cog，本目录不再维护，仅作历史留档。
EOT

git add README.md agent/README.md
git commit -m "docs(agent): 赛题3 迁移至 medpal-cog，本目录转为只读留档"
git push origin main

# 3) 关掉赛题3相关 PR，把新 PR 引导到新仓（gh 或网页操作）
```

## 5.5 第二批搬迁：旧仓未合并分支（2026-11-01）

切分只取了旧 `main`。旧仓还有 4 组成果躺在**未合并分支**上，已按文件搬进本仓（不是 merge，不带旧目录结构）：

```bash
cd /e/deepseek-data/medpal-cog
git fetch /e/deepseek-data/medpal 'refs/remotes/origin/*:refs/remotes/legacy/*'
# 逐个取文件后改包前缀（agent.ontology → ontology、agent.parse → parse）
```

| 来源分支 | 搬入 | 适配 |
| --- | --- | --- |
| `feat/agent-T4-ontology-diff` | `ontology/diff.py`（382 行）、`tests/test_ontology_diff.py`（18 测试） | `from agent.ontology.diff` → `from ontology.diff` |
| `feat/agent-T5-pdf-parse` | `parse/pdf.py`（98 行）、`parse/__init__.py`、`tests/test_pdf_parse.py`（4 测试） | 同上，包前缀；`fitz` 仍是 lazy import |
| `feat/t3-visual` | `web/trace.html`（288 行，静态页） | 无 |
| `docs/t1-t3-input-contract` | `docs/T3-可视化输入契约.md`、`docs/handoff/W1-T3-决策链可视化.md`、`tests/fixtures/trace_v1_broken.json`、`trace_walking_skeleton_example.json` | 文档里 `agent/` 前缀去掉 |

有两组**没有**搬：`docs/t1-ontology-schema` 的 schema 内容本仓 `docs/ontology-schema.md` 已是超集；`T6-w1-env-doc` 的 `docs/agent/env.md`（320 行）是 `docs/env.md`（340 行）的子集。`feat/t5-model-channel` 的 `tools/probe_llm.py` 与本仓完全一致（都 125 行）。

搬完验证：`python -m pytest tests -q` → **43 passed**（未装 PyMuPDF 时 PDF 用例 1 条 skipped），`python tools/acceptance.py` 全 PASS。

旧仓剩余分支（`legacy/*` 本地引用）作历史留档，不再合并；需要哪份就按上表的方式取文件。

## 6 改名注意

新仓暂定名 `medpal-cog`。若最终改成别的名字，只需替换三处：`README.md` 的 `git clone` 行、`docs/adr/ADR-001-仓库拆分与历史迁移.md` 标题下的仓名、本文件的表格；其余相对链接不受影响。

## 7 回滚

新仓可整仓删除重来；旧仓未做任何历史改写，`agent/` 与 `main` 保持在切分时的状态。需要重来就重跑 `git subtree split -P agent`——同样的输入会得到同样的提交链。
