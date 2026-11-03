# MedPal-Cog · 可进化医疗决策智能体

> **赛题3**｜基于华为 ModelEngine Nexent 打造可进化决策智能体
> 三人（T1 队长 / T2 / T3）· **2026-11-30 交付** · 本仓是赛题3 的唯一交付仓

只切一条链路：**门诊主诉 → 跨文档取证 → 科室与检查建议**。把赛题四条要求各做成一件能跑、能验、能溯源的东西：

**1 个自研 MCP Server（10 个工具）+ 3 个 Nexent Skill 包 + 1 个主智能体。**

---

## 1 现在能跑到哪一步

| 能力 | 状态 | 证据（一条命令） |
| --- | --- | --- |
| MCP Server，10 个工具 | **可跑** | `python mcp-server/server.py`（stdio）／`MCP_TRANSPORT=streamable-http python mcp-server/server.py`（Nexent 远程链接） |
| 数据资产台账 | **61 张 Asset Card**（文本 21 / 表格 20 / 图文 20） | `data/asset-cards/`，`data/samples/` 三类各 20 份 |
| 本体 v0.9 | **37 三元组 + 43 锚点**（seed 手写 17 + 跨文档长 20） | `python mcp-server/seed.py --reset` → `python tools/ingest_all.py` |
| 3 个 Skill 包 | **可导入** | `skills/s1-asset-audit`、`s2-ontology-evolve`、`s3-evidence-decision` |
| 主智能体配置 v0 | **已在 Nexent v2.7.0 实跑** | `agent/prompt.md` + `agent/config.json`；实跑记录 `agent/sessions/real-w1-01.json`（常态）、`real-w1-02.json`（冲突）；接线见 `agent/README.md` |
| 离线评测 | **20 条，六项指标 100%** | `python eval/run_eval.py`（**不是答辩分**，见 §6） |
| Walking Skeleton | **一条命令通电** | `python skeleton.py` |
| 本体版本差分 | **可回放**（新增/删除/修改 + 编号漂移对账） | `python -m pytest tests/test_ontology_diff.py -q`（18 条） |
| 智能体配置自洽 | **6 条测试**（白名单 = 服务端 10 工具、样例符合三行契约） | `python -m pytest tests/test_agent_config.py -q` |
| PDF 解析 | **页码锚点**（`p{页}.s{节}`） | `python -m pytest tests/test_pdf_parse.py -q`（4 条，缺 PyMuPDF 自动跳过） |
| 决策链可视化 | **静态页可开**（断链标红，无后端） | 浏览器打开 `web/trace.html`，拖入 `tests/fixtures/trace_v1_broken.json` |
| 测试总量 | **43 passed**（缺 PyMuPDF 时 1 skipped） | `python -m pytest tests -q` |
| Nexent 平台本体 | **已拉起 v2.7.0**（13 容器，控制台 :3000） | `docs/env.md` §2.5 四条判定命令 |
| MCP 远程接入 | 待接（W1） | 三条路径见 §7；接入记录见 `docs/env.md` §2.3 |

一条命令自检全部：`python tools/selfcheck.py`。
验收标准（16 项结构 + 7 项指标，带阈值）：`python tools/acceptance.py --with-eval`，口径见 [冲刺计划 §10](docs/冲刺计划-1130.md)。

---

## 2 赛题四条要求 → 交付物 → 怎么验

| # | 赛题要求 | 我们的交付物 | 怎么验 |
| --- | --- | --- | --- |
| R1 | 多模态异构数据的统一识别、理解与资产标识 | 解析器插件 + Asset Card 台账 | 打开 `data/asset-cards/`，每份文件都有模态、来源、版本、敏感级、可引用锚点 |
| R2 | 低资源本体的半自动构建、持续更新、与行业标准对齐 | 抽取 → 校验 → 对齐 → 发布 + 本体 v0.9 快照 | `python mcp-server/seed.py --reset` 出快照；`onto_propose` → `onto_commit` 后版本 +1 |
| R3 | 深度集成 MCP 与 Skills 编排 | 自研 MCP Server（10 工具）+ 3 个 Skill 包 | Nexent 控制台能看到 10 个工具；S1/S2/S3 三个技能能跑通 |
| R4 | 跨文档多跳、决策链可溯源、Skill 模板可复用 | Trace 数据结构 + 决策链报告 + 模板导出 | 任取一条问答，每步都挂 `anchor_id`；`trace_write` 出报告，`skill_export` 出模板 |
| R5 | 智能体基于 Nexent 可运行 | 远程 MCP 接入 + 主智能体配置 | 控制台里点开主智能体，按 §7 联调 |

### 2.1 「可进化」到底指什么（演示时三条都要出）

1. **本体会长**：新文档进来 → `onto_propose` 出候选三元组（新增 / 修正 / 废弃）→ 人工确认 → `onto_commit` 版本 +1 → 旧版本可 diff、可回滚。
2. **决策会变**：本体 v0.9 → v1.0 后，同一批题的回答**会变化**，且变化可解释（新证据命中、旧结论被推翻）。这是加分点。
3. **能力会沉**：一次成功执行 → `skill_export` 导出 SKILL.md 草稿 → 下次同类问题少走几步。

---

## 3 架构

```text
┌──────────────────────────────────────────────────────────────┐
│  交互层   Nexent Web（Next.js）· 演示页 · 决策链报告导出      │
├──────────────────────────────────────────────────────────────┤
│  编排层   Nexent Agent（主智能体 MedPal-Cog）                 │
│           + Skill S1 资产清点 / S2 本体进化 / S3 跨文档取证    │
│           检索-推理双驱动：先召回证据，再迭代推理，缺证据回退   │
├──────────────────────────────────────────────────────────────┤
│  工具层   自研 MCP Server（FastMCP · streamable-http :8090）  │
│           ingest · card · kg_query · onto_propose             │
│           std_align · onto_commit · trace_write · skill_export │
├──────────────────────────────────────────────────────────────┤
│  本体层   三元组存储（SQLite）· 版本快照 · 标准对齐映射表       │
│           冷启动：ICD-10 编码表 + 临床路径 + 药品说明书         │
├──────────────────────────────────────────────────────────────┤
│  数据层   Nexent 知识库（向量 + 全文）· MinIO 原件             │
│           解析器 text / pdf / table / image · Asset Card 台账  │
├──────────────────────────────────────────────────────────────┤
│  平台层   Nexent 基础设施：PostgreSQL · Elasticsearch          │
│           Redis · MinIO · config / runtime / mcp / data-process│
└──────────────────────────────────────────────────────────────┘
```

设计取舍（为什么自研 MCP、为什么 SQLite 不用 Neo4j、为什么只有 3 个 Skill）见 [方案 v1.2 §3.2](docs/赛题3-方案-v1.2.md)。

---

## 4 90 秒跑起来（纯离线，不需要 Docker）

```bash
python -m pip install -r requirements.txt

# 1) 建种子库（17 三元组 + 15 锚点），再把 61 份样例入台账并长出跨文档本体（37 三元组 + 43 锚点）
python mcp-server/seed.py --reset
python tools/ingest_all.py

# 2) 冒烟 + 三套测试
python -m pytest tests -q                 # 期望：43 passed（未装 PyMuPDF 时 1 skipped）

# 3) 离线评测，出报告到 eval/reports/
python eval/run_eval.py                   # 期望：六项指标 100%

# 4) 一条命令看全链路
python skeleton.py                        # 期望：OK 5 steps | 科室=消化内科 | 溯源完整率=0.75

# 5) 验收：16 项结构不变量 + 7 项指标阈值（FAIL 非零退出）
python tools/acceptance.py --with-eval
```

**Windows 两个必踩的坑**（别浪费半天）：

1. 控制台默认 GBK：任何跑 Python 的命令前加 `set PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING="utf-8"`），否则报告文件正常、终端全乱码。
2. 系统代理会拦 `127.0.0.1:8090`：联调 HTTP 时显式设 `NO_PROXY=127.0.0.1,localhost`，否则 httpx 报 `502 Bad Gateway`，看着像服务没起。

---

## 5 十个 MCP 工具

| 工具 | 对应 | 一句话 |
| --- | --- | --- |
| `ingest_asset` | R1 | 吃一份文件，解析、抽实体、生成 Asset Card 与锚点 |
| `get_asset_card` | R1 | 按 id / 模态 / 实体查卡片 |
| `kg_query` | R2 | 从种子实体出发取 k 跳路径，每条带 `triple_id` 与 provenance |
| `onto_propose` | R2 | 从资产里抽候选三元组，进待审队列（不直接入库） |
| `onto_commit` | R2 | 人工确认后提交，版本 +1，生成快照 |
| `std_align` | R2 | 实体 → ICD-10 映射，返回 exact / fuzzy / none |
| `trace_write` | R4 | 落决策链，算溯源完整率，出 Markdown 报告 |
| `skill_export` | R4 | 把一条 trace 的步骤序列导成 SKILL.md 草稿 |
| `kb_search` | 辅助 | 透传 Nexent 知识库检索（未配 `KB_ENDPOINT` 时返回配置提示） |
| `health` | 辅助 | 版本、库路径、三元组数、当前本体版本 |

约定：所有工具返回 `{"ok": true|false, ...}`；`ok=false` 必须带 `reason` 与 `hint`，不许静默失败。契约见 [docs/mcp-contract.md](docs/mcp-contract.md)。

---

## 6 评测：20 条离线分不等于答辩分

`eval/run_eval.py` 跑的是**规则化链路**，题目是我们自己出的，只用于回归与上限参照：

| 指标 | 当前 |
| --- | --- |
| 科室准确率 | 100% |
| 检查项准确率（Jaccard） | 100% |
| 检查项完全一致率 | 100% |
| 冲突召回 | 100% |
| 证据召回 | 100% |
| 溯源完整率 | 100% |

真实分数必须在 Nexent 里用**同一份** `eval/dataset/v0.jsonl` 跑平台评测任务，两套分数对不上就说明智能体层有额外损耗。评测集见 [eval/dataset/README.md](eval/dataset/README.md)。

---

## 7 接进 Nexent（三条路，W2 至少打通一条）

| 路径 | 做法 | 适用 |
| --- | --- | --- |
| ① 远程 MCP 链接（首选） | `MCP_TRANSPORT=streamable-http python mcp-server/server.py` → Nexent 里填 `http://host.docker.internal:8090/mcp` | 容器内访问宿主机 |
| ② API 转 MCP | 用 `server.py` 的工具签名写一份 OpenAPI 3.x 导入 | ① 联调不通时的兜底 |
| ③ 容器化同网 | `docker compose up`（见 [deploy/](deploy/README.md)），与 Nexent 同网络 | 要长期稳定跑 |

验证：`python tests/test_http_client.py`（先设 `NO_PROXY`）。

---

## 8 边界与合规

**做**：自由文本主诉 + 检验报告图片 + 门诊记录表格 → 实体归一 → 本体多跳 → 跨文档取证 → 冲突检测 → 科室与检查建议 + 证据锚点 + 决策链。

**不做**（评审时主动说明）：诊断结论、处方剂量、影像 AI 判读、多轮长对话随访、真实医院系统对接。

**数据**：只用公开标准与合成数据；仓库内 `synthetic` / `public` 两类标注，**不得存放任何真实患者数据、真实身份证号、真实手机号或医疗单据原图**。

**医学口径**：ICD-10 只做实体归一，不做鉴别推理；「上腹痛需除外消化性溃疡」这类临床知识只能来自临床路径 / 指南 / 说明书，并挂对应 `anchor_id`。

---

## 9 目录

```text
.
├── mcp-server/        FastMCP 服务：server / store / parsers / seed
├── skills/            3 个 Nexent Skill 包（S1 资产 / S2 本体 / S3 取证决策）
├── eval/              离线评测、评测集、Code 评估器
├── data/              61 张 Asset Card + 三类模态样本
├── tools/             trace 校验 / 夹具生成 / 模型通道探针 / 样本生成
├── tests/             冒烟、stdio 客户端、HTTP 客户端、trace schema
├── deploy/            Dockerfile + compose（Nexent 接入）
├── docs/              方案 v1.2、契约、schema、ADR、迁移说明
├── skeleton.py        Walking Skeleton：一条命令通电的最小主线
└── tools/selfcheck.py 一键自检
```

---

## 10 文档地图

| 想知道什么 | 看哪 |
| --- | --- |
| 技术方案（历史快照：六人排期与旧数字口径均已作废，只看技术判断） | [docs/赛题3-方案-v1.2.md](docs/赛题3-方案-v1.2.md) |
| 工具契约与错误码 | [docs/mcp-contract.md](docs/mcp-contract.md) |
| 本体 schema | [docs/ontology-schema.md](docs/ontology-schema.md) |
| trace 结构 | [docs/trace-schema.md](docs/trace-schema.md) |
| 角色与每周任务 | [docs/任务卡-三人版.md](docs/任务卡-三人版.md) |
| 工程规则 | [docs/rules.md](docs/rules.md) |
| 为什么单独建这个仓 | [docs/adr/ADR-001-仓库拆分与历史迁移.md](docs/adr/ADR-001-仓库拆分与历史迁移.md) |
| 历史怎么搬过来的 | [docs/migration.md](docs/migration.md) |
| 评审怎么走 | [docs/judge-guide.md](docs/judge-guide.md) |

---

## 11 协作

- **`main` 已开保护**：非管理员直推被拒、必走 PR + **≥1 approve** + CI 三绿（`lint (ruff)` / `test (pytest)` / `pipeline (skeleton + eval)`）；T1 的 admin 阀门是已知例外，见 [git-flow §4.1](docs/git-flow.md)。
- 分支：`feat/{模块}-{简述}`、`fix/{模块}-{简述}`、`docs/{简述}`、`chore/{简述}`。
- 提交：`type(scope): 中文动宾`，scope 见 [docs/rules.md](docs/rules.md)。
- 合并门槛：CI 三绿 + `tools/acceptance.py` 无 FAIL + 一张 approve（**交接单不进门槛**，周闸门核对证据位时才查）。
- **T1（队长）唯一 merge 权**；T1 自己的 PR 由 T2 或 T3 approve。
- 完整动线与卡点排查：[docs/git-flow.md](docs/git-flow.md)；见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 12 团队与许可

三人制（2026-11-01 起，截止 11-30）：

| 代号 | 账号 | 角色 |
| --- | --- | --- |
| **T1**（队长） | xiangyuli494-cmyk | 环境与 Nexent 集成、主智能体、跨文档演示、答辩材料、唯一 merge 权 |
| **T2** | `zincumyu` | 本体与推理（**难任务优先**）：本体 v0.9→v1.1、`kg_query` 多跳、`onto_propose`/`onto_commit`、差分与回滚、`std_align` |
| **T3** | `Dewqian` | 数据、评测与交付：Asset Card、PDF 解析去重与接入、30 条评测、3 个 Skill 包、镜像与视频 |

`CODEOWNERS` 与上表已用真实账号；分支保护在两人都接受邀请后切 `ENFORCE_ADMINS=1`（见 issue #9）。

排期见 [docs/冲刺计划-1130.md](docs/冲刺计划-1130.md)，每人每周任务见 [docs/任务卡-三人版.md](docs/任务卡-三人版.md)。
旧六人分工（T1–T6）的文档已于 2026-11-02 删除，历史见 git 与旧仓 `medpal`；本仓不再保留任何现行六人计划。

代码与文档采用 [Apache License 2.0](LICENSE)。第三方数据来源、版本与许可见 [docs/赛题3-方案-v1.2.md](docs/赛题3-方案-v1.2.md) §4.3。
