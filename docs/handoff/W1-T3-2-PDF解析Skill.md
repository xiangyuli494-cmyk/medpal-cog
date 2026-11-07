# W1-T3-2 交接单：PDF解析Skill
交付人：Dewqian
任务：PDF解析Skill开发、评测、异常容错
交付分支：feature/w1-pdf-eval-baseline
关联PR：#20

## 一、本次交付物清单
1. 核心解析模块：`mcp-server/parsers.py` PdfParser，支持标题/段落/表格行提取，已增加异常容错
2. 评测验收脚本：`tools/acceptance.py`，baseline全绿，W1指标达标（三元组≥35）
3. 测试资产：6份基础PDF样本 + 5份异常PDF样本（加密、损坏、无文字、扫描件、空白页）
4. 测试用例：`tests/test_pdf_parser.py`，12个测试全通过
5. 预基线报告：`docs/handoff/W1-T1-pdf-eval-baseline-pre.md`

## 二、已验证项
- ✅ baseline验收：PASS 16 / FAIL 0 / MANUAL 3
- ✅ W1评测：三元组37条，满足W1阈值≥35
- ✅ 异常场景降级：缺失依赖、加密PDF、损坏PDF、无文本PDF返回标准化error_type
- ✅ Ruff代码规范检查修复，CI可通过
- ✅ 数字标题正则修复：避免把表格数值误判为标题

## 三、能力边界（不承诺）
- 不做OCR识别，扫描图片PDF直接返回 NO_EXTRACTABLE_TEXT
- 不解析复杂合并单元格、跨页超大表格
- 不提取图片、批注、表单
- 只支持本地文件路径输入
- PDF解析能力通过 `ingest_asset` 的 `pdf_text` 模态分支入库，不单独暴露为MCP工具

## 四、后续待办
1. 补充边界case测试集
2. 跑 `--stage final --with-eval` 完整终版评测
3. 整理最终评测报告

## 五、调用方式
通过 `ingest_asset(path="xxx.pdf")` 自动识别为 `pdf_text` 模态，返回 anchors 和 blocks。
出错时不抛异常，error_type 写入 metadata，blocks/anchors 为空数组。

## 六、备注
MANUAL项需要Docker，仅打印命令，不参与判定。
