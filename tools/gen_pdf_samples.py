"""生成6份PDF测试样本，用于PDF解析器基线评测"""
from pathlib import Path
import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples" / "pdf"
OUT_DIR.mkdir(exist_ok=True, parents=True)


def make_sample_01():
    """pdf_01_normal_text.pdf - 普通正文文档"""
    doc = fitz.open()
    page = doc.new_page()
    text = """
# 病历摘要
患者男性，42岁，因反复上腹痛2周就诊。
查体：腹软，上腹部轻压痛，无反跳痛。
辅助检查：胃镜提示慢性非萎缩性胃炎。
处置：抑酸护胃，清淡饮食，随访。
"""
    page.insert_text((50, 50), text, fontsize=12)
    doc.save(OUT_DIR / "pdf_01_normal_text.pdf")
    doc.close()


def make_sample_02():
    """pdf_02_table.pdf - 带表格"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "检验结果表", fontsize=14)
    rect = fitz.Rect(50, 80, 450, 180)
    table = page.new_table(rect=rect, cols=3, rows=4)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "结果"
    table.cell(0, 2).text = "参考值"
    table.cell(1, 0).text = "WBC"
    table.cell(1, 1).text = "6.2"
    table.cell(1, 2).text = "4-10"
    table.cell(2, 0).text = "Hb"
    table.cell(2, 1).text = "131"
    table.cell(2, 2).text = "120-160"
    table.cell(3, 0).text = "PLT"
    table.cell(3, 1).text = "215"
    table.cell(3, 2).text = "100-300"
    doc.save(OUT_DIR / "pdf_02_table.pdf")
    doc.close()


def make_sample_03():
    """pdf_03_number_title.pdf - 数字编号标题"""
    doc = fitz.open()
    page = doc.new_page()
    text = """
1. 主诉
间断胸闷3天。
2. 现病史
3天前劳累后出现胸闷，休息后缓解。
3. 既往史
高血压病史5年。
4. 初步诊断
高血压病1级
"""
    page.insert_text((50, 50), text, fontsize=12)
    doc.save(OUT_DIR / "pdf_03_number_title.pdf")
    doc.close()


def make_sample_04():
    """pdf_04_multipage.pdf - 多页文档"""
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), "第一页：入院记录\n患者信息、主诉、现病史", fontsize=12)
    p2 = doc.new_page()
    p2.insert_text((50, 50), "第二页：辅助检查\n心电图、影像学报告", fontsize=12)
    p3 = doc.new_page()
    p3.insert_text((50, 50), "第三页：治疗方案\n用药与随访计划", fontsize=12)
    doc.save(OUT_DIR / "pdf_04_multipage.pdf")
    doc.close()


def make_sample_05():
    """pdf_05_font_size.pdf - 字号区分标题"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "出院小结", fontsize=16)
    page.insert_text((50, 80), "【诊断】", fontsize=14)
    page.insert_text((50, 110), "2型糖尿病", fontsize=12)
    page.insert_text((50, 140), "【医嘱】", fontsize=14)
    page.insert_text((50, 170), "降糖治疗，监测血糖", fontsize=12)
    doc.save(OUT_DIR / "pdf_05_font_size.pdf")
    doc.close()


def make_sample_06():
    """pdf_06_image_mix.pdf - 简单图文混合 PDF"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "胸片报告", fontsize=14)
    page.insert_text((50, 80), "影像描述：双肺纹理清晰。", fontsize=12)
    # 占位矩形模拟图片区域
    page.draw_rect(fitz.Rect(50, 120, 300, 280), color=(0, 0, 0))
    page.insert_text((50, 300), "印象：未见明显异常", fontsize=12)
    doc.save(OUT_DIR / "pdf_06_image_mix.pdf")
    doc.close()


if __name__ == "__main__":
    make_sample_01()
    make_sample_02()
    make_sample_03()
    make_sample_04()
    make_sample_05()
    make_sample_06()
    print("全部6份PDF样本生成完成")
