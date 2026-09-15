#!/usr/bin/env python3
# build_docx.py
# แปลง docs/report/chapter4_results_th.md เป็น .docx รูปแบบวิทยานิพนธ์ระดับปริญญาเอก
# (TH Sarabun New, ตาราง/ภาพครบ, สอดคล้องกับไฟล์ผลลัพธ์จริงใน data/)
#
# วิธีใช้: python3 docs/report/build_docx.py

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MD_PATH = REPO_ROOT / "docs" / "report" / "chapter4_results_th.md"
OUT_PATH = REPO_ROOT / "docs" / "report" / "บทที่4_ผลการทดลอง_PhD.docx"

FONT_NAME = "TH Sarabun New"
BODY_SIZE = Pt(16)
H1_SIZE = Pt(22)
H2_SIZE = Pt(20)
H3_SIZE = Pt(18)
H4_SIZE = Pt(16)

ACCENT = RGBColor(0x1F, 0x3A, 0x5F)
HEADER_FILL = "1F3A5F"

# แผนที่ "ภาพที่ x.y ... (data/figures/.../fig_....png)" -> path ไฟล์จริงบนดิสก์
FIGURE_LINE_RE = re.compile(r"^\*\*ภาพที่\s+([\d.]+)\*\*\s*(.+)$")
FIGURE_FILE_RE = re.compile(r"`([^`]+\.(?:png|jpg|jpeg))`")
TABLE_CAPTION_RE = re.compile(r"^\*\*ตารางที่\s+([\d.]+)\*\*\s*(.+)$")


def set_font(run, size=BODY_SIZE, bold=None, italic=None, color=None):
    run.font.name = FONT_NAME
    run.font.size = size
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_NAME)
    rFonts.set(qn("w:cs"), FONT_NAME)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color


def add_run(paragraph, text, **kwargs):
    r = paragraph.add_run(text)
    set_font(r, **kwargs)
    return r


INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def add_rich_text(paragraph, text, base_size=BODY_SIZE):
    """แยกข้อความ inline markdown (bold **x**, code `x`) แล้วเติมเป็น run"""
    tokens = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            add_run(paragraph, tok[2:-2], size=base_size, bold=True)
        elif tok.startswith("`") and tok.endswith("`"):
            r = paragraph.add_run(tok[1:-1])
            r.font.name = "Menlo"
            r.font.size = Pt(base_size.pt - 2)
            r.font.color.rgb = RGBColor(0x8A, 0x2B, 0x06)
        else:
            add_run(paragraph, tok, size=base_size)


def add_heading(doc, text, level):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level > 1 else 20)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    size = {1: H1_SIZE, 2: H2_SIZE, 3: H3_SIZE, 4: H4_SIZE}.get(level, H4_SIZE)
    r = p.add_run(text)
    set_font(r, size=size, bold=True, color=ACCENT if level <= 2 else None)
    if level == 1:
        pPr = p._p.get_or_add_pPr()
        bdr = pPr.makeelement(qn("w:pBdr"), {})
        bottom = pPr.makeelement(qn("w:bottom"), {
            qn("w:val"): "single", qn("w:sz"): "12", qn("w:space"): "4", qn("w:color"): HEADER_FILL,
        })
        bdr.append(bottom)
        pPr.append(bdr)
    return p


def add_body_paragraph(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.25
    add_rich_text(p, text)
    return p


def add_bullet(doc, text, ordered_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(4)
    if ordered_prefix:
        add_run(p, ordered_prefix, bold=True)
    add_rich_text(p, text)
    return p


def set_cell_shading(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.makeelement(qn("w:shd"), {
        qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hex_color,
    })
    tcPr.append(shd)


def split_md_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def add_table_caption(doc, num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    add_run(p, f"ตารางที่ {num} ", bold=True)
    add_rich_text(p, text)
    return p


def add_figure_caption(doc, num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, f"ภาพที่ {num} ", bold=True)
    add_rich_text(p, text)
    return p


def add_md_table(doc, header_cells, data_rows):
    n_cols = len(header_cells)
    table = doc.add_table(rows=1, cols=n_cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    hdr = table.rows[0].cells
    for i, text in enumerate(header_cells):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_rich_text(p, text, base_size=Pt(14))
        for run in p.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_shading(hdr[i], HEADER_FILL)

    for row_idx, row_cells in enumerate(data_rows):
        row = table.add_row().cells
        for i, text in enumerate(row_cells):
            if i >= n_cols:
                break
            row[i].text = ""
            p = row[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i > 0 else WD_ALIGN_PARAGRAPH.LEFT
            add_rich_text(p, text, base_size=Pt(14))
        if row_idx % 2 == 1:
            for c in row:
                set_cell_shading(c, "F0F3F7")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_code_block(doc, lines):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(10)
    pPr = p._p.get_or_add_pPr()
    shd = pPr.makeelement(qn("w:shd"), {
        qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): "F5F5F5",
    })
    pPr.append(shd)
    for i, line in enumerate(lines):
        if i > 0:
            p.add_run().add_break()
        r = p.add_run(line if line else " ")
        r.font.name = "Menlo"
        r.font.size = Pt(12)
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    return p


def add_cover_page(doc):
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "รายงานผลการทดลอง", size=Pt(30), bold=True, color=ACCENT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "บทที่ 4: ผลการทดลอง (Results)", size=Pt(24), bold=True)

    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(
        p,
        "Comparative Performance Benchmarking of Quantum Micro-Simulators "
        "Across Diverse Microcontroller Architectures for Edge Computing",
        size=Pt(18), italic=True,
    )

    for _ in range(6):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "จัดทำสำหรับการเสนอผลการทดลองระดับปริญญาเอก (PhD Dissertation)", size=Pt(16))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_run(p, "สร้างจากข้อมูลผลการทดลองจริงใน data/ (Phase 1–4)", size=Pt(14), italic=True,
            color=RGBColor(0x60, 0x60, 0x60))

    doc.add_page_break()


def add_toc_placeholder(doc):
    p = doc.add_paragraph()
    add_run(p, "สารบัญ", size=H1_SIZE, bold=True, color=ACCENT)
    p2 = doc.add_paragraph()
    add_run(
        p2,
        "หมายเหตุ: เปิดไฟล์นี้ใน Microsoft Word แล้วไปที่ References → Table of Contents "
        "เพื่อสร้างสารบัญอัตโนมัติจากหัวข้อ (Heading) ที่ฝังไว้ในเอกสารนี้",
        italic=True, color=RGBColor(0x60, 0x60, 0x60),
    )
    doc.add_page_break()


def set_page_setup(doc):
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.0)


def set_default_style(doc):
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = BODY_SIZE
    rpr = style.element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_NAME)
    rFonts.set(qn("w:cs"), FONT_NAME)


def resolve_figure_path(md_reference: str):
    m = FIGURE_FILE_RE.search(md_reference)
    if not m:
        return None
    rel = m.group(1)
    path = REPO_ROOT / rel
    return path if path.exists() else None


def main():
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    doc = Document()
    set_page_setup(doc)
    set_default_style(doc)

    add_cover_page(doc)
    add_toc_placeholder(doc)

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped == "" :
            i += 1
            continue

        if stripped == "---":
            i += 1
            continue

        if stripped.startswith("#### "):
            add_heading(doc, stripped[5:].strip(), 4)
            i += 1
            continue
        if stripped.startswith("### "):
            add_heading(doc, stripped[4:].strip(), 3)
            i += 1
            continue
        if stripped.startswith("## "):
            add_heading(doc, stripped[3:].strip(), 2)
            i += 1
            continue
        if stripped.startswith("# "):
            add_heading(doc, stripped[2:].strip(), 1)
            i += 1
            continue

        # Code block ```
        if stripped.startswith("```"):
            block = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            add_code_block(doc, block)
            continue

        # Table caption line -> ตามด้วยตาราง markdown
        m_tab_cap = TABLE_CAPTION_RE.match(stripped)
        if m_tab_cap:
            add_table_caption(doc, m_tab_cap.group(1), m_tab_cap.group(2))
            i += 1
            # ข้ามบรรทัดว่างถ้ามี
            while i < n and lines[i].strip() == "":
                i += 1
            # อ่านตาราง markdown
            if i < n and lines[i].strip().startswith("|"):
                header_cells = split_md_row(lines[i])
                i += 1
                if i < n and re.match(r"^\|?[\s:|-]+\|?$", lines[i].strip()):
                    i += 1
                data_rows = []
                while i < n and lines[i].strip().startswith("|"):
                    data_rows.append(split_md_row(lines[i]))
                    i += 1
                add_md_table(doc, header_cells, data_rows)
            continue

        # Standalone markdown table (ไม่มี caption "ตารางที่" นำหน้า)
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|?[\s:|-]+\|?$", lines[i + 1].strip()):
            header_cells = split_md_row(lines[i])
            i += 2
            data_rows = []
            while i < n and lines[i].strip().startswith("|"):
                data_rows.append(split_md_row(lines[i]))
                i += 1
            add_md_table(doc, header_cells, data_rows)
            continue

        # Figure caption line -> แทรกรูปจริงจากดิสก์
        m_fig = FIGURE_LINE_RE.match(stripped)
        if m_fig:
            fig_num, fig_text = m_fig.group(1), m_fig.group(2)
            img_path = resolve_figure_path(fig_text)
            i += 1
            # บรรทัดถัดไปอาจเป็น "ไฟล์: ..." แยกต่างหาก
            if i < n and lines[i].strip().startswith("ไฟล์:") and img_path is None:
                img_path = resolve_figure_path(lines[i])
                i += 1
            if img_path:
                doc.add_picture(str(img_path), width=Inches(6.2))
                last_p = doc.paragraphs[-1]
                last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption_text = FIGURE_FILE_RE.sub("", fig_text).strip()
            add_figure_caption(doc, fig_num, caption_text)
            continue

        # Bullet list (- หรือ ตัวเลข)
        if stripped.startswith(("- ", "* ")):
            add_bullet(doc, stripped[2:].strip())
            i += 1
            continue
        m_num = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m_num:
            add_bullet(doc, m_num.group(2), ordered_prefix=f"{m_num.group(1)}. ")
            i += 1
            continue

        # ข้อความปกติ (รวมบรรทัดต่อเนื่องจนกว่าจะว่างหรือเจอ pattern พิเศษ)
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if nxt == "" or nxt.startswith(("#", "|", "```", "- ", "* ")) \
               or TABLE_CAPTION_RE.match(nxt) or FIGURE_LINE_RE.match(nxt) \
               or re.match(r"^\d+\.\s+", nxt):
                break
            para_lines.append(nxt)
            i += 1
        add_body_paragraph(doc, " ".join(para_lines))

    doc.save(str(OUT_PATH))
    print(f"บันทึกไฟล์ -> {OUT_PATH}")


if __name__ == "__main__":
    main()
