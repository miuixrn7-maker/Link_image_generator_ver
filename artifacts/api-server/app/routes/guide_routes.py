import io
import re
import urllib.request
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.auth import is_authenticated, current_user
from app.templates import templates
from app.guide_content import SECTIONS, GUIDE_VERSION, GUIDE_DATE

_DEPLOY_MD = Path(__file__).parent.parent.parent / "README_VPS_DEPLOY_FULL.md"


def _parse_md_blocks(md_text: str) -> list:
    """Parse markdown into simple block list for PDF/DOCX rendering."""
    blocks = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(code_lines)))
            i += 1
            continue

        # Table (starts with |)
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            # Parse table: first row = headers, skip separator, rest = rows
            if len(table_lines) >= 2:
                headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
                rows = []
                for tl in table_lines[2:]:
                    rows.append([c.strip() for c in tl.strip("|").split("|")])
                blocks.append(("table", {"headers": headers, "rows": rows}))
            continue

        # Headings
        if stripped.startswith("# "):
            blocks.append(("h1", stripped[2:].strip()))
        elif stripped.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
        elif stripped.startswith("### "):
            blocks.append(("h3", stripped[4:].strip()))

        # Unordered list item
        elif re.match(r'^[-*] ', stripped):
            item_text = re.sub(r'^[-*] ', '', stripped)
            item_text = re.sub(r'`([^`]+)`', r'\1', item_text)
            blocks.append(("li", item_text))

        # Ordered list item
        elif re.match(r'^\d+\. ', stripped):
            item_text = re.sub(r'^\d+\. ', '', stripped)
            item_text = re.sub(r'`([^`]+)`', r'\1', item_text)
            blocks.append(("oli", item_text))

        # Horizontal rule
        elif stripped.startswith("---"):
            blocks.append(("hr", ""))

        # Non-empty paragraph
        elif stripped:
            # Strip inline code backticks and bold/italic markers
            clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
            clean = re.sub(r'`([^`]+)`', r'\1', clean)
            clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
            blocks.append(("p", clean))

        i += 1
    return blocks

router = APIRouter()

_FONTS_DIR = Path(__file__).parent.parent.parent / "data" / "fonts"
_FONT_PATH = _FONTS_DIR / "DejaVuSans.ttf"
_FONT_BOLD_PATH = _FONTS_DIR / "DejaVuSans-Bold.ttf"
_FONT_URL = "https://github.com/py-pdf/fpdf2/raw/refs/heads/master/test/fonts/DejaVuSans.ttf"
_FONT_BOLD_URL = "https://github.com/py-pdf/fpdf2/raw/refs/heads/master/test/fonts/DejaVuSans-Bold.ttf"


def _ensure_font():
    _FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for path, url in [(_FONT_PATH, _FONT_URL), (_FONT_BOLD_PATH, _FONT_BOLD_URL)]:
        if not path.exists():
            try:
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                raise RuntimeError(f"Не удалось загрузить шрифт: {e}")


@router.get("/guide", response_class=HTMLResponse)
async def guide_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "guide.html", {
        "user": current_user(request),
        "sections": SECTIONS,
        "version": GUIDE_VERSION,
        "guide_date": GUIDE_DATE,
    })


@router.get("/guide/download-pdf")
async def download_pdf(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    try:
        _ensure_font()
    except RuntimeError as e:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(f"Ошибка: {e}", status_code=500)

    from fpdf import FPDF

    class GuidePDF(FPDF):
        def header(self):
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(120, 120, 120)
            self.cell(0, 8, "Генератор прямых ссылок — Руководство пользователя", align="L")
            self.ln(1)
            self.set_draw_color(220, 220, 220)
            self.set_line_width(0.3)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)

        def footer(self):
            self.set_y(-13)
            self.set_font("DejaVu", "", 8)
            self.set_text_color(160, 160, 160)
            self.cell(0, 6, f"Стр. {self.page_no()} · Версия {GUIDE_VERSION} · {GUIDE_DATE}", align="C")

    pdf = GuidePDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(_FONT_PATH))
    pdf.add_font("DejaVu", "B", str(_FONT_BOLD_PATH))
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Title page area
    pdf.set_font("DejaVu", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(6)
    pdf.cell(0, 12, "Руководство пользователя", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"Версия {GUIDE_VERSION}  ·  {GUIDE_DATE}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_draw_color(200, 200, 220)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(10)

    for idx, sec in enumerate(SECTIONS, 1):
        # Section heading
        pdf.set_font("DejaVu", "B", 13)
        pdf.set_text_color(37, 99, 235)
        pdf.cell(0, 8, f"{idx}. {sec['title']}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30, 30, 30)
        pdf.ln(2)

        for block_type, block_data in sec["content"]:
            if block_type == "p":
                pdf.set_font("DejaVu", "", 10)
                pdf.multi_cell(0, 5.5, block_data)
                pdf.ln(2)

            elif block_type == "h3":
                pdf.set_font("DejaVu", "B", 10)
                pdf.set_text_color(50, 50, 50)
                pdf.ln(1)
                pdf.cell(0, 6, block_data, new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)

            elif block_type in ("ul", "ol"):
                pdf.set_font("DejaVu", "", 10)
                for i, item in enumerate(block_data, 1):
                    prefix = f"{i}." if block_type == "ol" else "•"
                    pdf.cell(7, 5.5, prefix)
                    pdf.multi_cell(0, 5.5, item)
                pdf.ln(2)

            elif block_type == "code":
                pdf.set_font("DejaVu", "", 8.5)
                pdf.set_fill_color(245, 245, 248)
                pdf.set_draw_color(210, 210, 220)
                pdf.set_line_width(0.2)
                pdf.set_text_color(60, 60, 80)
                for line in block_data.split("\n"):
                    pdf.cell(0, 5, "  " + line, new_x="LMARGIN", new_y="NEXT", fill=True, border="LR")
                pdf.set_text_color(30, 30, 30)
                pdf.ln(2)

            elif block_type == "table":
                pdf.set_font("DejaVu", "B", 9)
                pdf.set_fill_color(240, 242, 248)
                col_w = (pdf.w - pdf.l_margin - pdf.r_margin) / len(block_data["headers"])
                for h in block_data["headers"]:
                    pdf.cell(col_w, 6, h, border=1, fill=True)
                pdf.ln()
                pdf.set_font("DejaVu", "", 9)
                for row in block_data["rows"]:
                    for cell in row:
                        pdf.cell(col_w, 5.5, cell, border=1)
                    pdf.ln()
                pdf.ln(2)

        pdf.ln(4)
        pdf.set_draw_color(230, 230, 235)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)

    buf = io.BytesIO(bytes(pdf.output()))
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="rukovodstvo.pdf"'},
    )


@router.get("/guide/download-docx")
async def download_docx(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)

    from docx import Document
    from docx.shared import Pt, RGBColor, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2)

    # Title
    title = doc.add_heading("Руководство пользователя", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(f"Версия {GUIDE_VERSION}  ·  {GUIDE_DATE}")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].font.size = Pt(11)
    sub.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    doc.add_paragraph()

    for idx, sec in enumerate(SECTIONS, 1):
        h = doc.add_heading(f"{idx}. {sec['title']}", level=1)
        h.runs[0].font.color.rgb = RGBColor(37, 99, 235)

        for block_type, block_data in sec["content"]:
            if block_type == "p":
                p = doc.add_paragraph(block_data)
                p.style.font.size = Pt(10.5)

            elif block_type == "h3":
                h3 = doc.add_heading(block_data, level=3)
                h3.runs[0].font.color.rgb = RGBColor(50, 50, 50)

            elif block_type == "ul":
                for item in block_data:
                    doc.add_paragraph(item, style="List Bullet")

            elif block_type == "ol":
                for item in block_data:
                    doc.add_paragraph(item, style="List Number")

            elif block_type == "code":
                p = doc.add_paragraph(block_data)
                p.runs[0].font.name = "Courier New"
                p.runs[0].font.size = Pt(9)

            elif block_type == "table":
                tbl = doc.add_table(
                    rows=1 + len(block_data["rows"]),
                    cols=len(block_data["headers"]),
                )
                tbl.style = "Table Grid"
                hdr_cells = tbl.rows[0].cells
                for i, h_text in enumerate(block_data["headers"]):
                    hdr_cells[i].text = h_text
                    hdr_cells[i].paragraphs[0].runs[0].font.bold = True
                for r_idx, row in enumerate(block_data["rows"]):
                    row_cells = tbl.rows[r_idx + 1].cells
                    for c_idx, cell_text in enumerate(row):
                        row_cells[c_idx].text = cell_text
                doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="rukovodstvo_polzovatelya.docx"'},
    )


@router.get("/guide/download-deploy-pdf")
async def download_deploy_pdf(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    try:
        _ensure_font()
    except RuntimeError as e:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(f"Ошибка: {e}", status_code=500)

    md_text = _DEPLOY_MD.read_text(encoding="utf-8")
    blocks = _parse_md_blocks(md_text)

    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    class DeployPDF(FPDF):
        def header(self):
            self.set_font("DejaVu", "B", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 7, "Генератор прямых ссылок — Руководство по VPS", align="L")
            self.ln(1)
            self.set_draw_color(220, 220, 220)
            self.set_line_width(0.2)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

        def footer(self):
            self.set_y(-13)
            self.set_font("DejaVu", "", 8)
            self.set_text_color(160, 160, 160)
            self.cell(0, 6, f"Стр. {self.page_no()}", align="C")

    pdf = DeployPDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(_FONT_PATH))
    pdf.add_font("DejaVu", "B", str(_FONT_BOLD_PATH))
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(left=20, top=15, right=15)

    for btype, bdata in blocks:
        if btype == "h1":
            pdf.set_font("DejaVu", "B", 16)
            pdf.set_text_color(30, 30, 30)
            pdf.ln(2)
            pdf.multi_cell(0, 9, bdata)
            pdf.ln(2)

        elif btype == "h2":
            pdf.set_font("DejaVu", "B", 12)
            pdf.set_text_color(37, 99, 235)
            pdf.ln(3)
            pdf.multi_cell(0, 7, bdata)
            pdf.set_draw_color(200, 215, 250)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

        elif btype == "h3":
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(55, 65, 81)
            pdf.ln(2)
            pdf.multi_cell(0, 6, bdata)
            pdf.ln(1)

        elif btype == "p":
            pdf.set_font("DejaVu", "", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5.5, bdata)
            pdf.ln(1.5)

        elif btype == "li":
            pdf.set_font("DejaVu", "", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(6, 5.5, "•")
            pdf.multi_cell(0, 5.5, bdata)

        elif btype == "oli":
            pdf.set_font("DejaVu", "", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5.5, bdata)

        elif btype == "code":
            pdf.set_font("DejaVu", "", 8)
            pdf.set_fill_color(245, 246, 250)
            pdf.set_text_color(50, 50, 80)
            pdf.ln(1)
            for cline in bdata.split("\n"):
                safe = cline[:110]
                pdf.cell(0, 4.8, "  " + safe, fill=True, ln=True)
            pdf.set_text_color(40, 40, 40)
            pdf.ln(2)

        elif btype == "hr":
            pdf.set_draw_color(220, 220, 230)
            pdf.set_line_width(0.3)
            pdf.ln(2)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

        elif btype == "table":
            pdf.set_font("DejaVu", "B", 8.5)
            pdf.set_fill_color(237, 242, 252)
            pdf.set_text_color(40, 40, 40)
            avail = pdf.w - pdf.l_margin - pdf.r_margin
            col_w = avail / max(len(bdata["headers"]), 1)
            for h in bdata["headers"]:
                pdf.cell(col_w, 6, h[:30], border=1, fill=True)
            pdf.ln()
            pdf.set_font("DejaVu", "", 8.5)
            for row in bdata["rows"]:
                for cell in row:
                    pdf.cell(col_w, 5.5, str(cell)[:40], border=1)
                pdf.ln()
            pdf.ln(2)

    buf = io.BytesIO(bytes(pdf.output()))
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="vps_deploy_guide.pdf"'},
    )


@router.get("/guide/download-deploy-docx")
async def download_deploy_docx(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)

    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    md_text = _DEPLOY_MD.read_text(encoding="utf-8")
    blocks = _parse_md_blocks(md_text)

    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2)

    for btype, bdata in blocks:
        if btype == "h1":
            h = doc.add_heading(bdata, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.LEFT

        elif btype == "h2":
            h = doc.add_heading(bdata, level=1)
            if h.runs:
                h.runs[0].font.color.rgb = RGBColor(37, 99, 235)

        elif btype == "h3":
            h = doc.add_heading(bdata, level=2)

        elif btype == "p":
            p = doc.add_paragraph(bdata)
            p.paragraph_format.space_after = Pt(4)

        elif btype == "li":
            doc.add_paragraph(bdata, style="List Bullet")

        elif btype == "oli":
            doc.add_paragraph(bdata, style="List Number")

        elif btype == "code":
            p = doc.add_paragraph(bdata)
            if p.runs:
                p.runs[0].font.name = "Courier New"
                p.runs[0].font.size = Pt(8.5)

        elif btype == "table":
            if bdata["headers"] and bdata["rows"]:
                tbl = doc.add_table(
                    rows=1 + len(bdata["rows"]),
                    cols=len(bdata["headers"]),
                )
                tbl.style = "Table Grid"
                for i, h_text in enumerate(bdata["headers"]):
                    cell = tbl.rows[0].cells[i]
                    cell.text = h_text
                    if cell.paragraphs[0].runs:
                        cell.paragraphs[0].runs[0].font.bold = True
                for r_idx, row in enumerate(bdata["rows"]):
                    for c_idx, ct in enumerate(row):
                        tbl.rows[r_idx + 1].cells[c_idx].text = ct
                doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="vps_deploy_guide.docx"'},
    )
