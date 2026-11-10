#!/usr/bin/env python3
"""把 accounts.json 生成为横版 A4 Word 表格（可选 Excel）。

用法：
    python build_docx.py --config <work>/config.json --out "<输出路径>/xxx.docx" [--xlsx]
"""
import argparse
import json
import os
from collections import Counter

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

PRIMARY = RGBColor(0x8E, 0x3B, 0x6B)
MUTED = RGBColor(0x66, 0x66, 0x66)

COLS_MAIN = [
    ("序号", 1.2), ("昵称", 3.2), ("抖音号", 4.1), ("评论原文（判定依据）", 7.4),
    ("评论位置", 2.8), ("点赞", 1.1), ("来源视频", 5.9),
]
COLS_LINK = [("序号", 1.2), ("昵称", 3.4), ("主页链接", 21.1)]


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def no_split(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    trPr.append(el)


def set_cell(cell, text, size=9.5, bold=False, color=None, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(str(text))
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    if color is not None:
        run.font.color.rgb = color


def page_break_before(paragraph):
    paragraph.paragraph_format.page_break_before = True


def add_page_field(paragraph):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar"); fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar"); fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin); run._r.append(instr); run._r.append(fld_end)


def build_table(doc, headers, widths, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    hdr = table.rows[0]
    repeat_header(hdr)
    for i, (name, w) in enumerate(zip(headers, widths)):
        cell = hdr.cells[i]
        cell.width = Cm(w)
        set_cell(cell, name, size=9.5, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade(cell, "8E3B6B")

    for idx, row in enumerate(rows):
        r = table.add_row()
        no_split(r)
        for i, val in enumerate(row):
            cell = r.cells[i]
            cell.width = Cm(widths[i])
            set_cell(cell, val, size=9)
            if idx % 2 == 1:
                shade(cell, "FAF7F9")
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--xlsx", action="store_true")
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    d = cfg["date"]
    label = d["label"]
    accounts = json.load(open(cfg["paths"]["accounts"], encoding="utf-8"))
    report_txt = ""
    if os.path.exists(cfg["paths"]["report"]):
        report_txt = open(cfg["paths"]["report"], encoding="utf-8").read()

    stats = {}
    for line in report_txt.splitlines():
        if "：" in line:
            k, v = line.split("：", 1)
            stats[k.strip("# ")] = v

    doc = Document()
    # 清空文档属性，避免残留作者/单位等元信息
    cp = doc.core_properties
    cp.author = ""
    cp.last_modified_by = ""
    cp.title = f"{label} 生日 抖音账号汇总"
    cp.subject = "公开评论信息整理"
    cp.comments = ""
    cp.keywords = ""
    cp.category = ""

    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(1.8)

    # 页脚页码
    footer_p = sec.footer.paragraphs[0]
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_field(footer_p)

    # 封面
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("数据采集汇总报告"); r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = PRIMARY
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{label} 生日"); r.font.size = Pt(30); r.font.bold = True; r.font.color.rgb = PRIMARY
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("抖音评论区账号汇总"); r.font.size = Pt(30); r.font.bold = True; r.font.color.rgb = PRIMARY
    doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"评论区全量抓取 × 上下文判定 × {len(accounts)} 个确认账号")
    r.font.size = Pt(13); r.font.color.rgb = MUTED
    doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("采集方式：浏览器接管 + 抖音评论接口批量拉取（公历口径）")
    r.font.size = Pt(10); r.font.color.rgb = MUTED

    # 一、结论摘要
    h = doc.add_heading("一、结论摘要", level=1); page_break_before(h)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    total_scan = stats.get("扫描评论总数", "-")
    doc.add_paragraph(
        f"本轮共扫描 {total_scan} 条评论，最终确认 {len(accounts)} 个在评论区明确报出「{label}」出生的抖音账号。"
    )
    doc.add_paragraph(
        f"判定口径：评论原文中「年份与月日同时出现」才算命中，包括 "
        f"{d['y2']}{d['m2']}{d['d2']}、{d['y2']}.{d['m2']}.{d['d2']}、{d['y2']}年{d['month']}月{d['day']}、"
        f"{d['year']} {d['month']}.{d['day']} 等写法；"
        f"只写「{d['m2']}{d['d2']}」而未标年份的未计入主表；含「农历」字样的命中已剔除。"
    )
    if report_txt:
        note = doc.add_paragraph(report_txt.strip().split("\n\n")[-1] if "\n\n" in report_txt else "")
        for run in note.runs:
            run.font.size = Pt(9); run.font.color.rgb = MUTED

    # 二、账号明细
    h = doc.add_heading(f"二、账号明细（{len(accounts)} 人）", level=1); page_break_before(h)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    rows = []
    for a in accounts:
        pos = f"第{a['pos']}条" if a.get("pos") else "—"
        src = (a.get("video_desc") or a.get("video_author") or "")[:26] or "-"
        rows.append([a["no"], a.get("nickname") or "（未获取）", a.get("douyin_id") or "（未显示）",
                     (a.get("text") or "")[:70], pos, a.get("digg", 0), src])
    build_table(doc, [c[0] for c in COLS_MAIN], [c[1] for c in COLS_MAIN], rows)
    p = doc.add_paragraph()
    r = p.add_run("* 评论位置为采集时刻评论区默认排序的序号，会随评论增长变化；点赞 0 仅表示该条暂无点赞。")
    r.font.size = Pt(8); r.font.color.rgb = MUTED

    # 三、主页链接
    h = doc.add_heading("三、主页直达链接", level=1); page_break_before(h)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    rows = []
    for a in accounts:
        rows.append([a["no"], a.get("nickname") or "（未获取）", a.get("profile") or f"（未取到链接，可搜索抖音号 {a.get('douyin_id')}）"])
    build_table(doc, [c[0] for c in COLS_LINK], [c[1] for c in COLS_LINK], rows)

    # 四、方法说明
    h = doc.add_heading("四、采集方法说明（供复核）", level=1)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    methods = [
        "入口筛选：抖音网页版搜索同生日合集类关键词，按评论量锁定大评论区视频。",
        "全量拉取：捕获评论接口请求作为模板，在页面内并发翻页（8 路 × 20 条/批），单视频可拉数万条。",
        "锚点楼层：识别「年份+集合/包厢」类楼层并拉取全部回复，用上下文把只写月日的回复归位。",
        "判定去重：按「年份+月日」正则复核、按评论 ID 与文本去重、剔除农历口径。",
    ]
    for m in methods:
        doc.add_paragraph(m, style="List Number")

    # 五、备注
    h = doc.add_heading("五、备注与建议", level=1)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    notes = [
        "结果来自用户在公开评论区的主动留言，仅用于正当用途，互动时注意礼貌与隐私。",
        "评论区深处（最新评论）可能仍有未覆盖用户，如需扩大样本可提高采集上限后重跑。",
        "主页链接可直接在浏览器打开；若需要批量打开，可让执行方在单窗口多标签页中依次打开。",
    ]
    for n in notes:
        doc.add_paragraph(n, style="List Bullet")

    # 六、免责声明
    h = doc.add_heading("六、免责声明", level=1)
    for run in h.runs:
        run.font.color.rgb = PRIMARY
    disclaimers = [
        "本表仅整理用户在公开评论区主动发布的信息，不涉及任何非公开数据。",
        "使用者须自行确保用途合法合规，遵守《网络安全法》《个人信息保护法》及平台用户协议。",
        "严禁将本表用于骚扰、跟踪、营销骚扰、诈骗或其他侵害他人权益的行为。",
        "作者仅提供技术方法，不对使用者的使用行为及由此产生的任何后果承担法律责任。",
        "本表涉及个人信息，请勿公开传播、转卖或共享；使用完毕后建议及时删除。",
    ]
    for d in disclaimers:
        doc.add_paragraph(d, style="List Number")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    doc.save(args.out)
    print("docx ->", args.out, f"({len(accounts)} 行)")

    if args.xlsx:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook(); ws = wb.active; ws.title = "账号明细"
        ws.append([c[0] for c in COLS_MAIN])
        for a in accounts:
            ws.append([a["no"], a.get("nickname"), a.get("douyin_id"), a.get("text"),
                       a.get("pos"), a.get("digg"), (a.get("video_desc") or "")[:30]])
        head_fill = PatternFill("solid", fgColor="8E3B6B")
        for cell in ws[1]:
            cell.fill = head_fill
            cell.font = Font(color="FFFFFF", bold=True)
        for col, w in zip("ABCDEFG", [6, 22, 24, 60, 10, 8, 34]):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws2 = wb.create_sheet("主页链接")
        ws2.append(["序号", "昵称", "主页链接"])
        for a in accounts:
            ws2.append([a["no"], a.get("nickname"), a.get("profile")])
        for col, w in zip("ABC", [6, 22, 90]):
            ws2.column_dimensions[col].width = w
        xlsx = os.path.splitext(args.out)[0] + ".xlsx"
        wb.save(xlsx)
        print("xlsx ->", xlsx)


if __name__ == "__main__":
    main()
