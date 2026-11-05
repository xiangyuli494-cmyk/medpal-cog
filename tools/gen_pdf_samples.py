"""生成 6 份 PDF 测试样本，用于验证 PdfParser 的各种场景。

场景清单：
1. pdf_01_normal_text.pdf   — 带页码锚点的普通正文 PDF
2. pdf_02_table.pdf        — 多行表格 PDF（验证表格提取，backlog: 静默吞错）
3. pdf_03_number_title.pdf  — 标题含数字（2026年、3.5万）PDF（backlog: 正则误匹配）
4. pdf_04_multipage.pdf     — 跨页长文本 PDF，校验页码锚点跳转
5. pdf_05_font_size.pdf     — 字体大小差异大的标题 PDF（验证字体大小识别）
6. pdf_06_image_mix.pdf     — 简单图文混合 PDF
"""
from pathlib import Path
import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples" / "pdf"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def save(doc: fitz.Document, name: str):
    out = OUT_DIR / name
    doc.save(str(out))
    doc.close()
    print(f"  生成: {out.name} ({out.stat().st_size} bytes)")


# ============ 1. 普通正文 PDF（带页码锚点） ============
def gen_normal_text():
    doc = fitz.open()
    page = doc.new_page()
    text = """消化性溃疡诊疗指南

第一章 概述
消化性溃疡主要指发生于胃和十二指肠的慢性溃疡，是一多发病、常见病。溃疡的形成有各种因素，其中酸性胃液对黏膜的消化作用是溃疡形成的基本因素。

第二章 临床表现
上腹部疼痛是本病的主要症状。多位于上腹部，也可出现在左上腹部或胸骨、剑突后。常呈隐痛、钝痛、胀痛、烧灼样痛。

第三章 检查
1. 内镜检查
内镜检查是确诊消化性溃疡的主要方法。胃镜检查可以直接观察到胃黏膜的情况。

2. 幽门螺杆菌检测
幽门螺杆菌检测对于消化性溃疡的诊断和治疗具有重要意义。"""
    page.insert_text((72, 72), text, fontsize=12, fontname="china-s")
    save(doc, "pdf_01_normal_text.pdf")


# ============ 2. 多行表格 PDF ============
def gen_table():
    doc = fitz.open()
    page = doc.new_page()
    # 先写标题
    page.insert_text((72, 72), "常见消化系统疾病检查项目表", fontsize=14, fontname="china-s")
    # 用表格插入
    rows = [
        ["疾病名称", "首选检查", "次选检查", "禁忌"],
        ["消化性溃疡", "胃镜", "上消化道造影", "无"],
        ["幽门螺杆菌感染", "呼气试验", "胃镜活检", "近期服用PPI"],
        ["胃炎", "胃镜", "胃功能四项", "无"],
        ["胃食管反流病", "胃镜", "24小时pH监测", "无"],
    ]
    # 手绘表格线 + 文字
    y = 120
    row_h = 30
    col_w = [100, 100, 120, 100]
    x_start = 72
    for r, row in enumerate(rows):
        x = x_start
        for c, cell in enumerate(row):
            page.draw_rect(fitz.Rect(x, y, x + col_w[c], y + row_h))
            page.insert_text((x + 5, y + 18), cell, fontsize=10, fontname="china-s")
            x += col_w[c]
        y += row_h
    save(doc, "pdf_02_table.pdf")


# ============ 3. 标题含数字 PDF（正则误匹配 backlog） ============
def gen_number_title():
    doc = fitz.open()
    page = doc.new_page()
    text = """2026年临床消化科诊疗指南更新说明

本指南基于3.5万样本量的临床数据修订，涵盖消化性溃疡、胃炎等常见疾病的最新诊疗规范。

2025年回顾
2025年全国消化科门诊量达到1.2亿人次，其中消化性溃疡占比约8%。

3.5万样本说明
本次修订纳入了全国20家三甲医院共35000例临床病例数据，确保指南的科学性和权威性。

第四章 用药建议
质子泵抑制剂是治疗消化性溃疡的首选药物，疗程通常为4-8周。"""
    page.insert_text((72, 72), text, fontsize=12, fontname="china-s")
    save(doc, "pdf_03_number_title.pdf")


# ============ 4. 跨页长文本 PDF ============
def gen_multipage():
    doc = fitz.open()
    # 第1页
    page1 = doc.new_page()
    text1 = """第一章 消化性溃疡总论

消化性溃疡是临床常见的消化系统疾病之一，主要包括胃溃疡和十二指肠溃疡。本病的发作与季节变化有一定关系，秋冬和冬春之交是高发季节。

1.1 病因
消化性溃疡的病因主要包括以下几个方面：
- 幽门螺杆菌感染
- 药物因素（如NSAIDs、阿司匹林等）
- 遗传因素
- 饮食因素
- 精神因素

1.2 发病机制
酸性胃液对黏膜的消化作用是溃疡形成的基本因素。正常情况下，胃黏膜具有一系列防御和修复机制，能够抵御胃酸、胃蛋白酶的侵蚀。"""
    page1.insert_text((72, 72), text1, fontsize=12, fontname="china-s")

    # 第2页
    page2 = doc.new_page()
    text2 = """第二章 胃溃疡

2.1 临床表现
胃溃疡的临床表现与十二指肠溃疡有所不同。胃溃疡的疼痛多在餐后1小时内出现，经1～2小时后逐渐缓解，直至下餐进食后再复现上述节律。

2.2 诊断
胃镜检查是诊断胃溃疡的首选方法。胃镜下可见胃黏膜出现圆形或椭圆形的溃疡，底部洁白，边缘整齐。

第三章 十二指肠溃疡

3.1 临床表现
十二指肠溃疡的疼痛多在空腹时出现，餐后可缓解。疼痛部位多在右上腹。"""
    page2.insert_text((72, 72), text2, fontsize=12, fontname="china-s")
    save(doc, "pdf_04_multipage.pdf")


# ============ 5. 字体大小差异大的标题 PDF ============
def gen_font_size():
    doc = fitz.open()
    page = doc.new_page()
    # 大标题
    page.insert_text((72, 80), "消化性溃疡诊疗规范", fontsize=20, fontname="china-s")
    # 副标题（中等大小）
    page.insert_text((72, 120), "第一章 概述", fontsize=16, fontname="china-s")
    # 正文（小字号）
    body = """消化性溃疡主要指发生于胃和十二指肠的慢性溃疡，是一多发病、常见病。

第二章 检查方法
内镜检查是确诊消化性溃疡的主要方法。"""
    page.insert_text((72, 160), body, fontsize=10, fontname="china-s")
    save(doc, "pdf_05_font_size.pdf")


# ============ 6. 简单图文混合 PDF ============
def gen_image_mix():
    doc = fitz.open()
    page = doc.new_page()
    # 文字部分
    text = """消化性溃疡好发部位示意图

消化性溃疡最好发于胃角和十二指肠球部。下图展示了胃的解剖结构和溃疡常见发生部位。"""
    page.insert_text((72, 72), text, fontsize=12, fontname="china-s")
    # 插入一个简单的矩形当"图"
    page.draw_rect(fitz.Rect(100, 200, 400, 400), color=(0, 0, 1), fill=(0.9, 0.9, 1))
    page.insert_text((150, 300), "[胃解剖示意图]", fontsize=11, fontname="china-s")
    save(doc, "pdf_06_image_mix.pdf")


if __name__ == "__main__":
    print("开始生成 PDF 测试样本...")
    gen_normal_text()
    gen_table()
    gen_number_title()
    gen_multipage()
    gen_font_size()
    gen_image_mix()
    print(f"\n全部生成完毕，输出目录: {OUT_DIR}")
