"""生成带中文的测试PDF样本，避免乱码，可复现。"""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "samples" / "pdf" / "test_guide_01.pdf"


def main():
    doc = fitz.open()
    page = doc.new_page()
    # 用Windows系统自带微软雅黑字体，支持中文
    font_path = r"C:\Windows\Fonts\msyh.ttc"
    page.insert_font(fontname="msyh", fontfile=font_path)
    # 写入页前言（无标题，在第一个章节之前）
    pre_text = "这是就诊指南前言：患者出现上腹隐痛、反酸烧心症状，建议及时就诊。"
    page.insert_text((72, 72), pre_text, fontsize=11, fontname="msyh")
    # 章节标题
    page.insert_text((72, 120), "第一章 消化内科就诊指南", fontsize=14, fontname="msyh")
    page.insert_text((72, 160), "1.1 胃镜检查准备", fontsize=12, fontname="msyh")
    p1_text = "检查前需空腹8小时，停用抗凝药物，避免钡餐造影后短期内检查。"
    page.insert_text((72, 190), p1_text, fontsize=11, fontname="msyh")
    page.insert_text((72, 230), "1.2 幽门螺杆菌检测", fontsize=12, fontname="msyh")
    p2_text = "碳13呼气试验需要空腹，检查前4周停用抗生素、质子泵抑制剂。"
    page.insert_text((72, 260), p2_text, fontsize=11, fontname="msyh")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    doc.close()
    print(f"生成测试PDF成功: {OUT}")


if __name__ == "__main__":
    main()
