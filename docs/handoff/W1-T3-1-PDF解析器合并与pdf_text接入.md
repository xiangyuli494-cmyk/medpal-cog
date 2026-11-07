# W1‑T3‑1 交接单：PDF 解析器合并与 pdf_text 模态接入

表格

| 项 | 内容 |
| --- | --- |
| 任务编号 | W1‑T3‑1 |
| 负责人 | T3（Dewqian） |
| 依赖 | 无（W1 首批） |
| 分支 | feat/t3‑pdf‑final |
| PR | #15（已合并入 main，队长 approve） |
| 状态 | 已交付 |

## 一、目标

把仓库里并存的两套 PDF 解析实现合并为一套，将 PDF 以 pdf_text 模态接入 ingest_asset，产出带页码 / 章节锚点的资产卡，保证溯源证据链可定位、可去重。

## 二、交付物

表格

| 文件 | 变更 | 说明 |
| --- | --- | --- |
| mcp‑server/parsers.py | 修改 | 合并两套解析逻辑，统一为 PdfParser；anchor 三类分域；短段落过滤并计数 |
| tests/test_pdf_parser.py | 新增 | PDF 专项 5 条单元测试；整套 pytest 全量合计 16 用例 PASS，覆盖 anchor 唯一性、中文提取、标题识别、页前言锚点、短段落计数 |
| tools/gen_pdf_sample.py | 修改 | 用 PyMuPDF 内置 china‑s 字体生成中文样本，附文件大小断言 |
| data/samples/pdf/test_guide_01.pdf | 替换 | 旧样本用 Helvetica + CJK 码位硬塞，提取全是 U+FFFD；新样本 2.2 KB，中文正常 |
| tools/acceptance.py | 修改 | REQUIRED 清单移除已删除的 parse/pdf.py，补入新解析器与测试文件路径 |
| mcp‑server/data/ontology_v0.9.jsonl | 恢复 | 从 main 拉取原版快照，三元组回到 37 条，消除回退 |
| parse/pdf.py | 删除 | 旧解析器文件下线，parse/**init**.py 同步去掉旧导出 |
| mcp‑server/server.py、seed.py、ontology_grow.py、eval/run_eval.py | 修改 | 导入分组 / 排序对齐 ruff I 规则（E/F/I，行宽 100，py312） |
| data/samples/assets/AST‑2026‑7e430e.json | 修改 | 资产卡 source.path 由本机绝对路径改为仓库相对路径 |

## 三、关键实现

### 3.1 anchor 命名规则（P0‑1）

原实现页前言、小节标题、小节正文共用 `p{pno}.s1`，三个块撞成同一个 ID，溯源去重会把三条证据算成一条。现按块类型分域：

表格

| 块 | anchor_id | kind |
| --- | --- | --- |
| 页首无标题前言 | `p{pno}.pre` | page |
| 小节标题 | `p{pno}.h{sec}` | heading |
| 小节正文 | `p{pno}.s{sec}.p{n}` | paragraph |

实测：6 个 block 产生 6 个 anchor，ID 全局唯一。

### 3.2 中文样本（P0‑2）

弃用外部字体嵌入（原方案嵌微软雅黑，样本膨胀到 19 MB，远超 2 MB 阈值，且硬编码 `C:\Windows\Fonts` 跨平台不可用）
改用 PyMuPDF 内置 china‑s CJK 字体，样本体积 2.2 KB
生成脚本末尾加 `assert size < 300KB`，防止后续再次膨胀
测试断言 `page.get_text()` 能取到「消化 / 胃镜 / 幽门螺杆菌」，样本自身坏掉会被测出来

### 3.3 短段落过滤

低于 `PDF_MIN_SECTION_CHARS` 的段落不入块，丢弃数量写入 `ParsedDoc.metadata["skipped_short_paragraphs"]`。

## 四、验收证据

表格

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 代码规范 | `python -m ruff check .` | All checks passed |
| 单元测试 | `python -m pytest tests/test_pdf_parser.py -v` | 5 passed（PDF 专项），全量 16 用例 PASS |
| 必备文件清单 | `python tools/acceptance.py --stage baseline` | A‑13 PASS（21 项全在） |
| 样本体积 | `python tools/gen_pdf_sample.py` | 2.2 KB < 2 MB（A‑16） |
| 本体快照 | `Get‑Content mcp‑server/data/ontology_v0.9.jsonl \| Measure‑Object ‑Line` | 37 行，与 main 一致 |
| CI | GitHub Actions | lint /test/pipeline 三绿 |
| 队长终检 | PR #15 | PASS 16 / FAIL 0 / MANUAL 3，评测六项 100% |

## 五、遗留（不阻塞本 PR，转入下一轮）

1. **P1‑2 表格异常静默**：parsers.py 中 `find_tables()` 的 `except Exception` 把失败按「本页无表格」处理，表格抽取失败会静默变成数据缺失，台账上不可见。应把异常类型收窄到 PyMuPDF 相关异常，失败时写 `metadata["table_errors"]`。
2. **P2 标题正则误判**：`PDF_SECTION_RE` 会把「2026 年……」「3.5 万」判成标题，需补 3 条反例测试。
3. **P2 fixture 来源**：二进制 fixture 应由脚本产出而非只提交产物（本 PR 已加生成脚本，后续契约再收紧）。

## 六、下游

W1‑T3‑2 评测集 14 → 20 条（含两跳 6 条）：依赖本单交付的 pdf_text 资产卡。PDF 卡片需在 main 上稳定，评测基线才可复现，故 T3‑2 在本 PR 合并后启动。
本单合并后，资产卡 `AST‑2026‑7e430e` 已以 pdf_text 模态入库，可作为评测样本之一。

## 七、复现步骤

```
git checkout main && git pull
python tools/gen_pdf_sample.py          # 生成中文样本（2.2 KB 级）
python -m ruff check .
python -m pytest tests -q
python tools/acceptance.py --stage baseline
```