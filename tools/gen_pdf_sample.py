"""生成带中文的测试PDF样本，使用PyMuPDF内置CJK字体，文件体积小。"""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "samples" / "pdf" / "test_guide_01.pdf"


def main():
    doc = fitz.open()
    page = doc.new_page()
    # 使用PyMuPDF内置简体中文字体，不嵌入外部大字体，文件体积极小
    font_name = "china-s"
    # 写入页前言（无标题，在第一个章节之前）
    pre_text = "这是就诊指南前言：患者出现上腹隐痛、反酸烧心症状，建议及时就诊。"
    page.insert_text((72, 72), pre_text, fontsize=11, fontname=font_name)
    # 章节标题
    page.insert_text((72, 120), "第一章 消化内科就诊指南", fontsize=14, fontname=font_name)
    page.insert_text((72, 160), "1.1 胃镜检查准备", fontsize=12, fontname=font_name)
    p1_text = "检查前需空腹8小时，停用抗凝药物，避免钡餐造影后短期内检查。"
    page.insert_text((72, 190), p1_text, fontsize=11, fontname=font_name)
    page.insert_text((72, 230), "1.2 幽门螺杆菌检测", fontsize=12, fontname=font_name)
    p2_text = "碳13呼气试验需要空腹，检查前4周停用抗生素、质子泵抑制剂。"
    page.insert_text((72, 260), p2_text, fontsize=11, fontname=font_name)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    doc.close()
    # 断言文件大小，必须小于300KB（远小于2MB验收阈值）
    size_kb = OUT.stat().st_size / 1024
    print(f"生成测试PDF成功: {OUT}, 大小: {size_kb:.1f}KB")
    assert size_kb < 300, f"PDF文件过大: {size_kb:.1f}KB，超过阈值"


if __name__ == "__main__":
    main()
