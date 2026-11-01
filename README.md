# MedPal-Cog · 可进化医疗决策智能体

> **赛题3**｜基于华为 ModelEngine Nexent 打造可进化决策智能体
> 六人 · 2026-11-22 交付 · **本仓是赛题3 的唯一交付仓**

只切一条链路：**门诊主诉 → 跨文档取证 → 科室与检查建议**。把赛题四条要求各做成一件能跑、能验、能溯源的东西：

**1 个自研 MCP Server（10 个工具）+ 3 个 Nexent Skill 包 + 1 个主智能体。**

---

## 1 现在能跑到哪一步

| 能力 | 状态 | 证据（一条命令） |
| --- | --- | --- |
| MCP Server，10 个工具 | **可跑** | `python mcp-server/server.py`（stdio）／`MCP_TRANSPORT=streamable-http python mcp-server/server.py`（Nexent 远程链接） |
| 数据资产台账 | **61 张 Asset Card**（文本 21 / 表格 20 / 图文 20） | `data/asset-cards/`，`data/samples/` 三类各 20 份 |
| 本体 v0.9 种子 | **17 三元组 + 15 锚点** | `python mcp-server/seed.py --reset` |
| 3 个 Skill 包 | **可导入** | `skills/s1-asset-audit`、`s2-ontology-evolve`、`s3-evidence-decision` |
| 离线评测 | **14 条，六项指标 100%** | `python eval/run_eval.py`（**不是答辩分**，见 §6） |
| Walking Skeleton | **一条命令通电** | `python skeleton.py` |
| Nexent 平台本体 | 待 W2 接入 | 三条接入路径见 §7 |

一条命令自检全部：`python tools/selfcheck.py`。

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

# 1) 建种子库：17 三元组 + 1 份资产 + 15 个锚点
python mcp-server/seed.py --reset

# 2) 冒烟 + 三套测试
python -m pytest tests -q                 # 期望：17 passed, 1 skipped

# 3) 离线评测，出报告到 eval/reports/
python eval/run_eval.py                   # 期望：六项指标 100%

# 4) 一条命令看全链路
python skeleton.py                        # 期望：OK 5 steps | 科室=消化内科 | 溯源完整率=0.75
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

## 6 评测：14 条离线分不等于答辩分

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
| 全组唯一口径（方案） | [docs/赛题3-方案-v1.2.md](docs/赛题3-方案-v1.2.md) |
| 工具契约与错误码 | [docs/mcp-contract.md](docs/mcp-contract.md) |
| 本体 schema | [docs/ontology-schema.md](docs/ontology-schema.md) |
| trace 结构 | [docs/trace-schema.md](docs/trace-schema.md) |
| 角色与每周任务 | [docs/W1-角色任务卡.md](docs/W1-角色任务卡.md) |
| 工程规则 | [docs/rules.md](docs/rules.md) |
| 为什么单独建这个仓 | [docs/adr/ADR-001-仓库拆分与历史迁移.md](docs/adr/ADR-001-仓库拆分与历史迁移.md) |
| 历史怎么搬过来的 | [docs/migration.md](docs/migration.md) |
| 评审怎么走 | [docs/judge-guide.md](docs/judge-guide.md) |

---

## 11 协作

- 分支：`feat/agent-T{编号}-{简述}`、`fix/agent-T{编号}-{简述}`、`docs/agent-{简述}`；不直接 push `main`。
- 提交：`type(scope): 中文动宾`，scope 见 [docs/rules.md](docs/rules.md)。
- 合并门槛：CI 三绿（lint / pytest / skeleton+eval）+ 一份交接单（`docs/handoff/W{周}-T{编号}-{模块}.md`）。
- 详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 12 团队与许可

| 代号 | 账号 | 角色 |
| --- | --- | --- |
| T1 | xiangyuli494-cmyk | 架构与契约 |
| T2 | zincumyu | 知识工程与推理 |
| T3 | xy-Z5 | 前端与可视化 |
| T4 | Dewqian | 本体与标准对齐 |
| T5 | suyouZJF | 数据、检索与评测 |
| T6 | — | 环境、CI 与质量 |

代码与文档采用 [Apache License 2.0](LICENSE)。第三方数据来源、版本与许可见 [docs/赛题3-方案-v1.2.md](docs/赛题3-方案-v1.2.md) §4.3。
