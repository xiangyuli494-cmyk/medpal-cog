# PDF解析Skill MCP契约 v1
> 对齐项目MCP契约v1规范，T3-2交付

## 工具标识
name: pdf_parser
description: 对本地PDF文件做结构化解析，提取正文、标题块、表格行、锚点；自带容错降级，加密/损坏/缺少依赖时返回标准化错误，不抛异常栈。

## 入参（input）
```json
{
  "file_path": "string",
  "mode": "full | text-only",
  "enable_fallback": true
}
