"""PdfParser 单元测试，覆盖 anchor 唯一性、中文提取、块类型识别。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str((ROOT / "mcp-server").resolve()))

from parsers import PdfParser  # noqa: E402

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
