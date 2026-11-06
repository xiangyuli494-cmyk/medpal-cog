from __future__ import annotations
import time
from pathlib import Path
from typing import Any

from mcp import Tool
from mcp.types import TextContent

from ..parsers import PdfParser


def register_pdf_parser_tool() -> Tool:
    return Tool(
        name="pdf_parser",
        description="对本地PDF文件做结构化解析，提取正文、标题块、表格行、锚点；自带容错降级，加密/损坏/缺少依赖时返回标准化错误，不抛异常栈。",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地PDF文件绝对路径"},
                "mode": {
                    "type": "string",
                    "enum": ["full", "text-only"],
                    "default": "full",
                    "description": "full：提取文本+标题+表格；text-only：只提取纯文本",
                },
                "enable_fallback": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否开启容错降级",
                },
            },
            "required": ["file_path"],
        },
    )


async def handle_pdf_parser(arguments: dict[str, Any]) -> list[TextContent]:
    start = time.time()
    file_path = Path(arguments["file_path"])
    mode = arguments.get("mode", "full")
    enable_fallback = arguments.get("enable_fallback", True)

    result: dict[str, Any] = {
        "ok": True,
        "blocks": [],
        "anchors": [],
        "metadata": {"total_text_chars": 0, "parse_ms": 0},
        "error": None,
        "error_type": None,
    }

    try:
        parser = PdfParser()
        doc = parser.parse(file_path)
        result["blocks"] = [b.model_dump() for b in doc.blocks]
        result["anchors"] = doc.anchors
        result["metadata"]["total_text_chars"] = doc.metadata.get("chars", 0)

        if mode == "text-only":
            result["blocks"] = [
                b for b in result["blocks"] if b["type"] == "paragraph"
            ]

    except FileNotFoundError:
        result["ok"] = False
        result["error_type"] = "CORRUPTED_FILE"
        result["error"] = "文件不存在"
    except Exception as e:
        if not enable_fallback:
            raise
        result["ok"] = False
        result["error_type"] = "INTERNAL_ERROR"
        result["error"] = str(e)
    finally:
        result["metadata"]["parse_ms"] = int((time.time() - start) * 1000)

        return [TextContent(type="text", text=str(result))]
