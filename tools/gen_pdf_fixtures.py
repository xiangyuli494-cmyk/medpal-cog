"""生成 W2 T3-1 评测用的 PDF 样本（全部合成数据，不含真实患者信息）。

24 条用例里 16 条需要真实文件；这里一次生成全套，任何机器上按
`python tools/gen_pdf_fixtures.py && python eval/run_pdf_eval.py` 都能跑出同一份基线，
「可复现性」那一项就是靠这个成立。

覆盖的边界：正常单页 / 多页、章节标题、真表格、空白页、无文字层、生僻符号、
长文本、多级标题、0 字节、坏文件头、假扩展名、加密、无解析器、批量。

用法：python tools/gen_pdf_fixtures.py [--out tmp/pdf-fixtures]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "tmp" / "pdf-fixtures"

CJK = "china-s"
FIXED_DATE = "D:20261109000000+08'00'"

BODY = [
    "主诉：上腹隐痛三天，进食后加重，无呕血黑便。",
    "查体：腹软，上腹压痛阳性，无反跳痛，肝脾未触及。",
    "辅助检查：血常规提示血红蛋白 132 g/L，未见贫血。",
    "处理：完善幽门螺杆菌呼气试验，必要时行胃镜检查。",
    "随访：两周后门诊复诊，症状加重随时就诊。",
    "说明：本样本为合成数据，仅用于解析链路评测。",
]


def _put(page, text: str, x: float, y: float, size: int = 12) -> None:
    """写一行字；无中文字体时退回 ASCII，避免样本生成整体失败。"""
    try:
        page.insert_text((x, y), text, fontsize=size, fontname=CJK)
    except Exception:  # noqa: BLE001 - 字体缺失属可预期情况
        page.insert_text((x, y), text.encode("ascii", "replace").decode(), fontsize=size)


def _save(doc, path: Path) -> Path:
    doc.set_metadata(
        {
            "title": path.stem,
            "author": "medpal-cog",
            "producer": "medpal-cog fixtures",
            "creator": "medpal-cog",
            "creationDate": FIXED_DATE,
            "modDate": FIXED_DATE,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(path), garbage=4, deflate=True, no_new_id=True)
    except TypeError:  # 老版本 PyMuPDF 没有 no_new_id
        doc.save(str(path), garbage=4, deflate=True)
    doc.close()
    return path


def _text_pdf(path: Path, pages: list[list[str]]) -> Path:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=595, height=842)
        y = 72
        for line in lines:
            _put(page, line, 60, y)
            y += 22
    return _save(doc, path)


def normal_1page(out: Path) -> Path:
    return _text_pdf(out / "normal_1page.pdf", [BODY])


def normal_3page(out: Path) -> Path:
    pages = [[f"第 {i} 页：" + BODY[i % len(BODY)]] + BODY[1:4] for i in range(1, 4)]
    return _text_pdf(out / "normal_3page.pdf", pages)


def heading_doc(out: Path) -> Path:
    return _text_pdf(
        out / "heading_doc.pdf",
        [[
            "第一章 总论",
            BODY[0],
            BODY[1],
            "第二章 诊断依据",
            BODY[2],
            BODY[3],
        ]],
    )


def table_doc(out: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    rows = [
        ["检验项目", "单位", "参考区间"],
        ["白细胞计数", "10^9/L", "3.5-9.5"],
        ["血红蛋白", "g/L", "115-150"],
    ]
    x0, y0, w, h = 60, 120, 420, 84
    page.draw_rect(pymupdf.Rect(x0, y0, x0 + w, y0 + h), color=(0, 0, 0), width=1)
    for i in range(1, len(rows)):
        y = y0 + h * i / len(rows)
        page.draw_line((x0, y), (x0 + w, y), color=(0, 0, 0), width=1)
    for j in range(1, 3):
        x = x0 + w * j / 3
        page.draw_line((x, y0), (x, y0 + h), color=(0, 0, 0), width=1)
    for i, row in enumerate(rows):
        cy = y0 + h * (i + 0.5) / len(rows) + 4
        for j, cell in enumerate(row):
            _put(page, cell, x0 + w * j / 3 + 8, cy, size=11)
    _put(page, "表 1 检验参考区间（合成）", 60, 100, size=13)
    return _save(doc, out / "table_doc.pdf")


def blank_mixed(out: Path) -> Path:
    pages = [[BODY[0], BODY[1]], [" "], [BODY[2], BODY[3]]]
    return _text_pdf(out / "blank_mixed.pdf", pages)


def image_only(out: Path) -> Path:
    """只有矢量图、没有文字层：解析必须成功返回，且不产生空锚点。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(80, 100, 500, 400), color=(0.2, 0.2, 0.2), fill=(0.9, 0.9, 0.9))
    return _save(doc, out / "image_only.pdf")


def special_chars(out: Path) -> Path:
    lines = [
        "血压 ≥ 140/90 mmHg 记为升高，体温 36.5±0.2℃ 属正常。",
        "分级预防：①一级预防 ②二级预防 ③三级预防。",
        "剂量换算：1 g = 1000 mg；NaCl 0.9% 注射液 500 mL。",
        "符号保留测试：≥ ≤ ± × ÷ μ ° ‰ ① ② ③",
    ]
    return _text_pdf(out / "special_chars.pdf", [lines])


def long_text(out: Path) -> Path:
    pages = []
    for p in range(1, 9):
        lines = [
            f"{i}.{p} 长文本段落第 {p}-{i} 行，用于验证分页与分块不丢字。"
            for i in range(1, 31)
        ]
        pages.append(lines)
    return _text_pdf(out / "long_text.pdf", pages)


def nested_headings(out: Path) -> Path:
    return _text_pdf(
        out / "nested_headings.pdf",
        [[
            "1 概述",
            BODY[0],
            "1.1 背景",
            BODY[1],
            "1.1.1 细节",
            BODY[2],
            "2 结论",
            BODY[3],
        ]],
    )


def zero_byte(out: Path) -> Path:
    p = out / "zero_byte.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def broken_header(out: Path) -> Path:
    """文件头是 PDF、内部结构全坏：解析器必须降级，不许抛异常。"""
    p = out / "broken_header.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\ntrailer\n%%EOF\n")
    return p


def fake_ext(out: Path) -> Path:
    """扩展名是 .pdf，内容其实是纯文本。"""
    p = out / "fake_ext.pdf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes("这不是 PDF，只是一段文本。\n".encode())
    return p


def encrypted(out: Path) -> Path:
    p = out / "encrypted.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _put(page, BODY[0], 60, 90)
    _save(doc, out / "_encrypted_tmp.pdf")
    tmp = out / "_encrypted_tmp.pdf"
    with pymupdf.open(str(tmp)) as d:
        d.save(
            str(p),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-medpal",
            user_pw="user-medpal",
        )
    tmp.unlink()
    return p


def unsupported(out: Path) -> Path:
    p = out / "unsupported.xyz"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00\x01binary")
    return p


def batch(out: Path) -> list[Path]:
    """10 份内容各不相同的正常 PDF，用来验证批量入库的资产号不重复。"""
    made = []
    for i in range(1, 11):
        made.append(
            _text_pdf(
                out / "batch" / f"batch_{i:02d}.pdf",
                [[f"批量样本 {i:02d}：" + BODY[i % len(BODY)], BODY[(i + 2) % len(BODY)]]],
            )
        )
    return made


BUILDERS = {
    "normal_1page": normal_1page,
    "normal_3page": normal_3page,
    "heading_doc": heading_doc,
    "table_doc": table_doc,
    "blank_mixed": blank_mixed,
    "image_only": image_only,
    "special_chars": special_chars,
    "long_text": long_text,
    "nested_headings": nested_headings,
    "zero_byte": zero_byte,
    "broken_header": broken_header,
    "fake_ext": fake_ext,
    "encrypted": encrypted,
    "unsupported": unsupported,
    "batch": batch,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for name, fn in BUILDERS.items():
        fn(out)

    files = sorted(p for p in out.rglob("*.pdf") if p.is_file())
    print(f"样本 {len(files)} 份 -> {out}")
    print("另有 unsupported.xyz 1 份（无解析器用例）")
    return 0 if len(files) >= 23 else 1


if __name__ == "__main__":
    raise SystemExit(main())
