"""将 trace 打包成双击可开的报告；复用现有查看器，不修改前端契约。"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def export_html(trace: dict, source_note: str = "来源未核验") -> str:
    schema = json.loads((ROOT / "tools/trace.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(trace)
    viewer = (ROOT / "web/trace.html").read_text(encoding="utf-8")
    # JSON 不能提前闭合 script 标签；原查看器负责 HTML 文本转义。
    payload = json.dumps(trace, ensure_ascii=True).replace("<", "\\u003c")
    banner = "<p>来源：" + html.escape(source_note) + "；合成数据，非临床验证。</p>"
    bootstrap = (
        '<script type="application/json" id="embedded-trace">' + payload + "</script>"
        "<script>render(JSON.parse(document.getElementById('embedded-trace').textContent));"
        "</script>"
    )
    return viewer.replace('<div id="renderRoot">', banner + '<div id="renderRoot">').replace(
        "</body>", bootstrap + "\n</body>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-note", default="来源未核验")
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(export_html(trace, args.source_note), encoding="utf-8", newline="\n")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
