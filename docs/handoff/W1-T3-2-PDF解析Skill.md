# W1-T3-2 交接单：PDF解析Skill
交付人：Dewqian
任务：PDF解析Skill开发、评测、MCP契约封装
交付分支：feature/w1-pdf-eval-baseline
关联PR：#20

## 一、本次交付物清单
1. 核心解析模块：`mcp-server/parsers.py` PdfParser，支持标题/段落/表格行提取，已增加异常容错
2. 评测验收脚本：`tools/acceptance.py`，baseline全绿，W1指标达标（三元组≥35）
3. 测试资产：5份异常PDF样本（加密、损坏、无文字、扫描件、格式异常）
4. MCP契约文档：`docs/mcp-schema/pdf-parser-skill.md`
5. MCP工具封装：`mcp-server/tools/pdf_parser_tool.py`，注册函数+异步handler
6. 测试用例、yaml评测配置

## 二、已验证项
- ✅ baseline验收：PASS 16 / FAIL 0 / MANUAL 3
- ✅ W1评测：三元组37条，满足W1阈值≥35
- ✅ 异常场景降级：缺失依赖、加密PDF、损坏PDF、无文本PDF返回标准化error_type
- ✅ Ruff代码规范检查修复，CI可通过
- ✅ MCP入参、出参结构对齐项目MCP契约v1

## 三、能力边界（不承诺）
- 不做OCR识别，扫描图片PDF直接返回 NO_EXTRACTABLE_TEXT
- 不解析复杂合并单元格、跨页超大表格
- 不提取图片、批注、表单
- 只支持本地文件路径输入

## 四、后续待办（T3-2剩余）
1. 在MCP Server入口注册 `register_pdf_parser_tool`，加到工具列表
2. 补充边界case测试集
3. 跑 `--stage final --with-eval` 完整终版评测
4. 整理最终评测报告

## 五、调用方式
工具名：`pdf_parser`
入参：file_path、mode、enable_fallback
出错时 ok=false，error_type 按枚举返回，不抛原始异常栈。

## 六、备注
MANUAL项需要Docker，仅打印命令，不参与判定。
