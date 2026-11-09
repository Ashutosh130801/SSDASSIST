"""Files AI Assist produces: styled Excel / PDF / Word tables and Word / PDF documents (guides, letters, reports)."""
from __future__ import annotations

import io
import os
import re
from datetime import datetime

from .payroll_docs import FONT, FONT_B, _logo_file

ROOT = os.path.join(os.getcwd(), "uploads", "ai_files")
LABEL = lambda c: str(c).replace("_", " ").title()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _.-]+", "", name or "report").strip()[:80] or "report"


def table_xlsx(title: str, columns: list, rows: list[dict], subtitle: str = "") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = "Report"
    n = max(len(columns), 2)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
    c = ws.cell(1, 1, title); c.font = Font(bold=True, size=14, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
    c = ws.cell(2, 1, subtitle or f"Generated {datetime.now():%d-%b-%Y %H:%M} by AI Assist"); c.font = Font(size=9, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="2563EB")
    thin = Side(style="thin", color="CBD5E1"); B = Border(left=thin, right=thin, top=thin, bottom=thin)
    for j, col in enumerate(columns, 1):
        h = ws.cell(4, j, LABEL(col)); h.font = Font(bold=True, color="FFFFFF"); h.fill = PatternFill("solid", fgColor="1E3A8A")
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); h.border = B
    money = {c for c in columns if any(w in c for w in ("amount", "pending", "received", "outstanding", "collection", "net", "gross"))}
    for i, r in enumerate(rows, 5):
        for j, col in enumerate(columns, 1):
            v = r.get(col)
            if isinstance(v, (list, dict)):
                v = str(v)
            cell = ws.cell(i, j, v); cell.border = B
            if col in money and isinstance(v, (int, float)):
                cell.number_format = '₹ #,##0.00'
            if i % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F8FAFC")
    for j, col in enumerate(columns, 1):
        w = max([len(LABEL(col))] + [len(str(r.get(col) or "")) for r in rows[:200]])
        ws.column_dimensions[get_column_letter(j)].width = max(8, min(45, w + 2))
    ws.freeze_panes = "A5"
    if rows:
        ws.auto_filter.ref = f"A4:{get_column_letter(len(columns))}{4 + len(rows)}"
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


def _pdf(cfg, title, landscape=False):
    from fpdf import FPDF

    class _Doc(FPDF):
        # every multi_cell returns to the left margin on the next line (fpdf2 defaults to "right of the block")
        def multi_cell(self, *a, **k):
            k.setdefault("new_x", "LMARGIN"); k.setdefault("new_y", "NEXT")
            return super().multi_cell(*a, **k)

    pdf = _Doc("L" if landscape else "P", "mm", "A4")
    pdf.set_auto_page_break(True, 12)
    pdf.add_font("dv", "", FONT); pdf.add_font("dv", "B", FONT_B)
    pdf.add_page()
    W = pdf.w
    pdf.set_fill_color(30, 58, 138); pdf.rect(0, 0, W, 22, "F")
    logo = _logo_file(cfg or {})
    x0 = 10
    if logo:
        try:
            pdf.image(logo, 8, 3, h=16); x0 = 28
        except Exception:
            pass
    pdf.set_text_color(255, 255, 255); pdf.set_font("dv", "B", 13)
    pdf.set_xy(x0, 5); pdf.cell(W - x0 - 10, 7, title[:90])
    pdf.set_font("dv", "", 7.5); pdf.set_xy(x0, 12.5)
    pdf.cell(W - x0 - 10, 5, f"{(cfg or {}).get('company', {}).get('name') or ''} · generated {datetime.now():%d-%b-%Y %H:%M}")
    pdf.set_text_color(15, 23, 42); pdf.set_y(28)
    return pdf


def table_pdf(title, columns, rows, cfg=None) -> bytes:
    land = len(columns) > 6
    pdf = _pdf(cfg, title, land)
    usable = pdf.w - 20
    widths = []
    for c in columns:
        w = max([len(LABEL(c))] + [len(str(r.get(c) or "")) for r in rows[:100]])
        widths.append(min(max(w, 5), 40))
    scale = usable / sum(widths)
    widths = [w * scale for w in widths]
    pdf.set_font("dv", "B", 7.5); pdf.set_fill_color(30, 58, 138); pdf.set_text_color(255, 255, 255)
    for c, w in zip(columns, widths):
        pdf.cell(w, 7, LABEL(c)[:int(w / 1.5)], border=0, fill=True)
    pdf.ln(); pdf.set_text_color(15, 23, 42); pdf.set_font("dv", "", 7.2)
    for i, r in enumerate(rows):
        pdf.set_fill_color(*((248, 250, 252) if i % 2 else (255, 255, 255)))
        for c, w in zip(columns, widths):
            v = r.get(c)
            s = f"{v:,.2f}" if isinstance(v, float) else str(v if v is not None else "")
            pdf.cell(w, 6, s[:int(w / 1.45)], fill=True)
        pdf.ln()
    return bytes(pdf.output())


def doc_pdf(title, content: str, cfg=None) -> bytes:
    pdf = _pdf(cfg, title)
    for line in (content or "").splitlines():
        s = line.rstrip()
        if s.startswith("#"):
            pdf.ln(2); pdf.set_font("dv", "B", 12 if s.startswith("# ") else 10.5)
            pdf.multi_cell(0, 6, s.lstrip("# ").strip()); pdf.set_font("dv", "", 9.5)
        elif s.startswith(("- ", "* ")):
            pdf.set_font("dv", "", 9.5); pdf.multi_cell(0, 5, "•  " + s[2:].replace("**", ""))
        elif s == "":
            pdf.ln(2)
        else:
            pdf.set_font("dv", "", 9.5); pdf.multi_cell(0, 5, s.replace("**", ""))
    return bytes(pdf.output())


def doc_docx(title, content: str = "", columns=None, rows=None) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor
    d = Document()
    h = d.add_heading(title, level=0)
    for r in h.runs:
        r.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    d.add_paragraph(f"Generated {datetime.now():%d-%b-%Y %H:%M} by AI Assist").runs[0].font.size = Pt(8)
    for line in (content or "").splitlines():
        s = line.rstrip()
        if s.startswith("### "):
            d.add_heading(s[4:], level=3)
        elif s.startswith("## "):
            d.add_heading(s[3:], level=2)
        elif s.startswith("# "):
            d.add_heading(s[2:], level=1)
        elif s.startswith(("- ", "* ")):
            d.add_paragraph(s[2:].replace("**", ""), style="List Bullet")
        elif re.match(r"^\d+\. ", s):
            d.add_paragraph(re.sub(r"^\d+\. ", "", s).replace("**", ""), style="List Number")
        elif s:
            d.add_paragraph(s.replace("**", ""))
    if columns and rows is not None:
        t = d.add_table(rows=1, cols=len(columns))
        t.style = "Light Grid Accent 1"
        for j, c in enumerate(columns):
            t.rows[0].cells[j].text = LABEL(c)
        for r in rows[:2000]:
            cells = t.add_row().cells
            for j, c in enumerate(columns):
                v = r.get(c)
                cells[j].text = f"{v:,.2f}" if isinstance(v, float) else str(v if v is not None else "")
    out = io.BytesIO(); d.save(out)
    return out.getvalue()


def save(token: str, filename: str, data: bytes) -> str:
    os.makedirs(ROOT, exist_ok=True)
    path = os.path.join(ROOT, f"{token}_{_safe(filename)}")
    with open(path, "wb") as f:
        f.write(data)
    return path
