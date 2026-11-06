"""PdfParser 单元测试，覆盖 anchor 唯一性、中文提取、块类型识别。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str((ROOT / "mcp-server").resolve()))

from parsers import PdfParser, _pdf_is_heading  # noqa: E402

SAMPLE_PDF = ROOT / "data" / "samples" / "pdf" / "test_guide_01.pdf"


def test_anchor_ids_are_unique():
    """P0-1: 所有anchor_id全局唯一，不重复。"""
    parser = PdfParser()
    doc = parser.parse(SAMPLE_PDF)
    anchor_ids = [a["anchor_id"] for a in doc.anchors]
    assert len(anchor_ids) == len(set(anchor_ids)), \
        f"anchor ID重复: {[i for i in anchor_ids if anchor_ids.count(i) > 1]}"


def test_chinese_text_extracted():
    """P0-2: 能正确提取中文关键词，不是乱码。"""
    parser = PdfParser()
    doc = parser.parse(SAMPLE_PDF)
    full_text = doc.text()
    assert "消化" in full_text
    assert "胃镜" in full_text
    assert "幽门螺杆菌" in full_text


def test_heading_block_detected():
    """标题块识别正确，kind=heading，anchor格式是h序号。"""
    parser = PdfParser()
    doc = parser.parse(SAMPLE_PDF)
    headings = [b for b in doc.blocks if b.kind == "heading"]
    assert len(headings) >= 2
    heading_anchors = [a for a in doc.anchors if a["kind"] == "heading"]
    for a in heading_anchors:
        assert ".h" in a["anchor_id"], f"标题anchor格式错误: {a['anchor_id']}"


def test_page_preamble_anchor():
    """页首无标题前言的anchor是p*.pre，kind=page。"""
    parser = PdfParser()
    doc = parser.parse(SAMPLE_PDF)
    page_anchors = [a for a in doc.anchors if a["kind"] == "page"]
    assert len(page_anchors) >= 1
    assert ".pre" in page_anchors[0]["anchor_id"]


def test_skipped_short_counted():
    """短段落丢弃计数写入metadata。"""
    parser = PdfParser()
    doc = parser.parse(SAMPLE_PDF)
    assert "skipped_short_paragraphs" in doc.metadata
    assert doc.metadata["skipped_short_paragraphs"] >= 0


# ============ 异常 case 测试 ============

PDF_DIR = ROOT / "data" / "samples" / "pdf"


def test_encrypted_pdf_detected():
    """加密PDF被正确拦截，返回ENCRYPTED_PDF错误类型。"""
    parser = PdfParser()
    doc = parser.parse(PDF_DIR / "pdf_07_encrypted.pdf")
    assert doc.metadata.get("error_type") == "ENCRYPTED_PDF"
    assert "加密" in doc.metadata.get("error", "")
    assert len(doc.blocks) == 0
    assert len(doc.anchors) == 0


def test_scan_image_only_detected():
    """纯图片扫描件被正确识别，返回NO_EXTRACTABLE_TEXT。"""
    parser = PdfParser()
    doc = parser.parse(PDF_DIR / "pdf_08_scan_image_only.pdf")
    assert doc.metadata.get("error_type") == "NO_EXTRACTABLE_TEXT"
    assert "图片" in doc.metadata.get("error", "") or "扫描" in doc.metadata.get("error", "")
    assert len(doc.blocks) == 0


def test_blank_pdf_detected():
    """空白PDF被识别为无文本扫描件。"""
    parser = PdfParser()
    doc = parser.parse(PDF_DIR / "pdf_10_blank.pdf")
    assert doc.metadata.get("error_type") == "NO_EXTRACTABLE_TEXT"
    assert len(doc.blocks) == 0


def test_cross_page_table_parsed():
    """跨页表格PDF能正常解析，不崩溃。"""
    parser = PdfParser()
    doc = parser.parse(PDF_DIR / "pdf_09_cross_page_table.pdf")
    assert doc.metadata.get("pages") == 2
    table_rows = [b for b in doc.blocks if b.kind == "table_row"]
    assert len(table_rows) >= 5


def test_long_text_multipage():
    """多页长文本PDF解析正常，页数正确。"""
    parser = PdfParser()
    doc = parser.parse(PDF_DIR / "pdf_11_long_text.pdf")
    assert doc.metadata.get("pages") == 6
    assert doc.metadata.get("total_text_chars", 0) > 0


# ============ 正则误判反向测试（评审要求） ============

def test_number_text_not_heading():
    """反向用例：'3.5万样本说明' 不应被识别为标题。"""
    assert _pdf_is_heading("3.5万样本说明") is False


def test_pure_number_not_heading():
    """反向用例：纯数字/小数行（表格数值）不应被识别为标题。"""
    assert _pdf_is_heading("5.8") is False
    assert _pdf_is_heading("123.45") is False
