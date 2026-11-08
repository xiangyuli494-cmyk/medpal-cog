"""用 PdfParser 解析 6 份测试样本，输出解析结果用于基线记录。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

from parsers import PdfParser  # noqa: E402

PDF_DIR = ROOT / "data" / "samples" / "pdf"
FILES = [
    "pdf_01_normal_text.pdf",
    "pdf_02_table.pdf",
    "pdf_03_number_title.pdf",
    "pdf_04_multipage.pdf",
    "pdf_05_font_size.pdf",
    "pdf_06_image_mix.pdf",
    "pdf_07_encrypted.pdf",
    "pdf_08_scan_image_only.pdf",
    "pdf_09_cross_page_table.pdf",
    "pdf_10_blank.pdf",
    "pdf_11_long_text.pdf",
]

parser = PdfParser()

for fname in FILES:
    path = PDF_DIR / fname
    print(f"\n{'='*60}")
    print(f"文件: {fname}")
    print(f"{'='*60}")
    doc = parser.parse(path)
    print(f"页数: {doc.metadata.get('pages', '?')}")
    print(f"块总数: {len(doc.blocks)}")
    print(f"锚点总数: {len(doc.anchors)}")
    print(f"跳过短段落: {doc.metadata.get('skipped_short_paragraphs', '?')}")
    print("\n块类型分布:")
    kinds = {}
    for b in doc.blocks:
        kinds[b.kind] = kinds.get(b.kind, 0) + 1
    for k, v in kinds.items():
        print(f"  {k}: {v}")
    print("\n标题块:")
    for b in doc.blocks:
        if b.kind == "heading":
            print(f"  - {b.text[:50]}")
    print("\n前3个锚点:")
    for a in doc.anchors[:3]:
        print(f"  {a['anchor_id']} [{a['kind']}] {a['text'][:40]}")
