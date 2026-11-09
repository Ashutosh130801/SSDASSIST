"""Payroll documents: payslip PDF, salary register, bank upload file (any bank, template-driven),
PF ECR text, ESI and Professional-Tax statements."""
from __future__ import annotations

import base64
import csv
import io
import os
import re
from datetime import date, datetime

from .payroll_engine import words_inr

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
FONT = os.path.join(ASSETS, "fonts", "DejaVuSans.ttf")
FONT_B = os.path.join(ASSETS, "fonts", "DejaVuSans-Bold.ttf")
DEFAULT_LOGO = os.path.join(ASSETS, "ssd_logo.png")


def mask(acct: str | None) -> str:
    a = re.sub(r"\s", "", acct or "")
    return ("X" * max(0, len(a) - 4) + a[-4:]) if a else "—"


def money(v) -> str:
    return "₹ {:,.2f}".format(float(v or 0))


def _hex(c: str, fallback=(30, 58, 138)):
    try:
        c = (c or "").lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) if len(c) == 6 else fallback
    except ValueError:
        return fallback


def _logo_file(cfg) -> str | None:
    uri = (cfg.get("company") or {}).get("logo") or ""
    if uri.startswith("data:image/"):
        try:
            head, b64 = uri.split(",", 1)
            ext = "png" if "png" in head else "jpg"
            p = os.path.join(os.path.dirname(FONT), f"_logo_cache.{ext}")
            data = base64.b64decode(b64)
            if not os.path.exists(p) or open(p, "rb").read() != data:
                with open(p, "wb") as f:
                    f.write(data)
            return p
        except Exception:
            return None
    return DEFAULT_LOGO if (cfg.get("company") or {}).get("use_default_logo", True) and os.path.exists(DEFAULT_LOGO) else None


MONTHS = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def period_label(period: str) -> str:
    return f"{MONTHS[int(period[5:7])]} {period[:4]}"


def _d(x) -> str:
    return x.strftime("%d-%b-%Y") if isinstance(x, (date, datetime)) else (str(x) if x else "—")


# ───────────────────────────────────────────────────────────── payslip PDF
def payslip_pdf(items: list[tuple], cfg: dict) -> bytes:
    """items = [(run, line, ytd_dict_or_None)] → one page per employee."""
    from fpdf import FPDF
    co = cfg.get("company") or {}
    ps = cfg.get("payslip") or {}
    NAVY = _hex(ps.get("accent"))
    SOFT, LINE, GREY, INK = (239, 244, 255), (203, 213, 225), (100, 116, 139), (15, 23, 42)
    logo = _logo_file(cfg)
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(False)
    pdf.add_font("dv", "", FONT)
    pdf.add_font("dv", "B", FONT_B)
    for run, line, ytd in items:
        s = line.snapshot or {}
        att = line.attendance or {}
        pdf.add_page()
        pdf.set_fill_color(*NAVY); pdf.rect(0, 0, 210, 34, "F")
        x0 = 12
        if logo:
            try:
                pdf.image(logo, 12, 6, h=22); x0 = 40
            except Exception:
                x0 = 12
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(x0, 8); pdf.set_font("dv", "B", 14); pdf.cell(110, 7, (co.get("name") or "")[:48])
        pdf.set_xy(x0, 16); pdf.set_font("dv", "", 7.3); pdf.multi_cell(108, 3.5, (co.get("address") or "")[:220], align="L")
        pdf.set_xy(150, 8); pdf.set_font("dv", "B", 13); pdf.cell(48, 7, (ps.get("title") or "PAYSLIP")[:14], align="R")
        pdf.set_xy(150, 16); pdf.set_font("dv", "", 9); pdf.cell(48, 5, period_label(run.period), align="R")
        pdf.set_xy(130, 22); pdf.set_font("dv", "", 7); pdf.cell(68, 4, f"Cycle {_d(run.cycle_start)} → {_d(run.cycle_end)}", align="R")

        y = 40
        pdf.set_fill_color(*SOFT); pdf.set_draw_color(*LINE); pdf.rect(10, y, 190, 44, "DF")
        info = [("Employee name", s.get("name")), ("Employee ID", s.get("emp_code")), ("Designation", s.get("designation")),
                ("Location", s.get("location")), ("Date of joining", s.get("joining_date")), ("PAN", s.get("pan")),
                ("Bank", s.get("bank_name")), ("Account no.", s.get("account_masked")), ("IFSC", s.get("ifsc")),
                ("UAN", s.get("uan")), ("ESIC no.", s.get("esic_number")),
                ("Paid days / LOP", f"{line.attendance.get('paid_days_final', att.get('paid_days', '—'))} / {att.get('lop', 0)}")]
        for i, (k, v) in enumerate(info):
            cx, cy = 14 + (i % 3) * 63, y + 3.5 + (i // 3) * 10
            pdf.set_xy(cx, cy); pdf.set_font("dv", "", 6.6); pdf.set_text_color(*GREY); pdf.cell(60, 3.5, k.upper())
            pdf.set_xy(cx, cy + 3.8); pdf.set_font("dv", "B", 8.8); pdf.set_text_color(*INK); pdf.cell(60, 4.5, str(v or "—")[:30])

        y = 90
        earns = [(e["name"], e["amount"]) for e in (line.earnings or []) if float(e.get("amount") or 0) or not e.get("adjustment")]
        deds = [(d["name"], d["amount"]) for d in (line.deductions or [])]
        rows = max(len(earns), len(deds), 1)
        rh = 6.6 if rows <= 10 else 5.4
        for x, title, items_ in ((10, "EARNINGS", earns), (106, "DEDUCTIONS", deds)):
            pdf.set_fill_color(*NAVY); pdf.rect(x, y, 94, 7.5, "F")
            pdf.set_text_color(255, 255, 255); pdf.set_font("dv", "B", 8.3)
            pdf.set_xy(x + 3, y + 1.5); pdf.cell(55, 5, title)
            pdf.set_xy(x + 50, y + 1.5); pdf.cell(41, 5, "Amount", align="R")
            yy = y + 7.5
            for j in range(rows):
                pdf.set_fill_color(*((248, 250, 252) if j % 2 else (255, 255, 255))); pdf.rect(x, yy, 94, rh, "F")
                if j < len(items_):
                    k, v = items_[j]
                    pdf.set_text_color(*INK); pdf.set_font("dv", "", 8)
                    pdf.set_xy(x + 3, yy + (rh - 4.5) / 2); pdf.cell(58, 4.5, str(k)[:34])
                    pdf.set_xy(x + 50, yy + (rh - 4.5) / 2); pdf.cell(41, 4.5, money(v), align="R")
                yy += rh
            pdf.set_draw_color(*LINE); pdf.rect(x, y, 94, yy - y + 8)
            pdf.set_fill_color(*SOFT); pdf.rect(x, yy, 94, 8, "F")
            pdf.set_font("dv", "B", 8.6); pdf.set_text_color(*NAVY)
            tot = line.gross if title == "EARNINGS" else line.total_deductions
            pdf.set_xy(x + 3, yy + 1.8); pdf.cell(55, 4.5, "Gross earnings" if title == "EARNINGS" else "Total deductions")
            pdf.set_xy(x + 50, yy + 1.8); pdf.cell(41, 4.5, money(tot), align="R")
        y = y + 7.5 + rows * rh + 14

        pdf.set_fill_color(22, 101, 52); pdf.rect(10, y, 190, 19, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(15, y + 2.5); pdf.set_font("dv", "", 7.8); pdf.cell(80, 4, "NET PAY")
        pdf.set_xy(15, y + 7.5); pdf.set_font("dv", "B", 16); pdf.cell(80, 8, money(line.net))
        pdf.set_xy(92, y + 5); pdf.set_font("dv", "", 8); pdf.multi_cell(104, 4, words_inr(line.net), align="R")
        y += 24

        pdf.set_text_color(*INK)
        if ps.get("show_attendance", True):
            pdf.set_font("dv", "B", 7.3); pdf.set_text_color(*GREY); pdf.set_xy(10, y); pdf.cell(190, 4, "ATTENDANCE")
            pdf.set_font("dv", "", 7.8); pdf.set_text_color(*INK); pdf.set_xy(10, y + 4.5)
            pdf.cell(190, 4.5, f"Days in cycle {att.get('cycle_days', '—')}   Present {att.get('present', 0):g}   Leave {att.get('leave', 0):g}   "
                               f"Absent {att.get('absent', 0):g}   Week-offs {att.get('weekoff', 0)}   Late {att.get('late', 0)}   LOP {att.get('lop', 0):g}")
            y += 11
        if ps.get("show_employer", True) and line.employer:
            pdf.set_font("dv", "B", 7.3); pdf.set_text_color(*GREY); pdf.set_xy(10, y); pdf.cell(190, 4, "EMPLOYER CONTRIBUTIONS (not deducted from your pay)")
            pdf.set_font("dv", "", 7.8); pdf.set_text_color(*INK); pdf.set_xy(10, y + 4.5)
            pdf.cell(190, 4.5, "   ".join(f"{e['name']}: {money(e['amount'])}" for e in line.employer)[:150])
            y += 11
        if ps.get("show_ytd", True) and ytd:
            pdf.set_font("dv", "B", 7.3); pdf.set_text_color(*GREY); pdf.set_xy(10, y); pdf.cell(190, 4, f"YEAR TO DATE ({ytd.get('fy', '')})")
            pdf.set_font("dv", "", 7.8); pdf.set_text_color(*INK); pdf.set_xy(10, y + 4.5)
            pdf.cell(190, 4.5, f"Gross {money(ytd.get('gross'))}   Deductions {money(ytd.get('deductions'))}   Net {money(ytd.get('net'))}   "
                               f"PF {money(ytd.get('pf'))}   TDS {money(ytd.get('tds'))}")
            y += 11
        pdf.set_font("dv", "B", 7.3); pdf.set_text_color(*GREY); pdf.set_xy(10, y); pdf.cell(190, 4, "PAYMENT")
        pdf.set_font("dv", "", 7.8); pdf.set_text_color(*INK); pdf.set_xy(10, y + 4.5)
        mode = {"bank": "Bank transfer", "cash": "Cash", "cheque": "Cheque"}.get(s.get("payment_mode") or "bank", "Bank transfer")
        pdf.cell(190, 4.5, f"Pay date: {_d(run.pay_date)}    Mode: {mode}    Status: {'Paid' if line.pay_status == 'paid' else 'Processed'}"
                           + (f"    UTR: {line.utr}" if line.utr else ""))
        if line.hold:
            pdf.set_text_color(220, 38, 38); pdf.set_font("dv", "B", 8.5); pdf.set_xy(10, y + 12)
            pdf.cell(190, 5, "SALARY ON HOLD — released when the hold is cleared", align="C")

        pdf.set_draw_color(*LINE); pdf.line(10, 282, 200, 282)
        pdf.set_text_color(*GREY); pdf.set_font("dv", "", 6.6)
        pdf.set_xy(10, 283.5); pdf.cell(140, 4, (co.get("footer") or "")[:120])
        pdf.set_xy(140, 283.5); pdf.cell(60, 4, f"Ref PR{run.id}-{line.id}", align="R")
        if co.get("signatory"):
            pdf.set_xy(140, 276); pdf.set_font("dv", "", 7); pdf.cell(60, 4, f"For {co.get('name') or ''}"[:40], align="R")
    return bytes(pdf.output())


# ───────────────────────────────────────────────────────────── register (Excel)
def _xl_styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color="CBD5E1")
    return dict(B=Border(left=thin, right=thin, top=thin, bottom=thin),
                head=dict(font=Font(bold=True, color="FFFFFF", size=10), fill=PatternFill("solid", fgColor="1E3A8A"),
                          alignment=Alignment(horizontal="center", vertical="center", wrap_text=True)),
                Font=Font, Fill=PatternFill, Align=Alignment)


def _banner(ws, title, sub, ncol, X):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ncol, 2))
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(ncol, 2))
    c = ws.cell(1, 1, title); c.font = X["Font"](bold=True, size=14, color="FFFFFF"); c.fill = X["Fill"]("solid", fgColor="1E3A8A")
    c = ws.cell(2, 1, sub); c.font = X["Font"](size=9, color="FFFFFF"); c.fill = X["Fill"]("solid", fgColor="2563EB")
    ws.row_dimensions[1].height = 26


def register_xlsx(run, lines, cfg) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    X = _xl_styles()
    INR = '₹ #,##0.00'
    co = cfg.get("company") or {}
    wb = Workbook()
    inc = [l for l in lines if l.included]
    # Summary
    ws = wb.active; ws.title = "Summary"
    _banner(ws, f"{co.get('name') or 'Payroll'} — Salary {period_label(run.period)}",
            f"Cycle {_d(run.cycle_start)} to {_d(run.cycle_end)} · Pay date {_d(run.pay_date)} · Status {run.status.upper()}", 2, X)
    t = run.totals or {}
    rows = [("Employees paid", t.get("count", 0)), ("Excluded / exempt", t.get("excluded", 0)), ("On hold", t.get("on_hold", 0)),
            ("Gross earnings", t.get("gross", 0)), ("Total deductions", t.get("deductions", 0)), ("NET PAYABLE", t.get("net", 0)),
            ("Employer contributions", t.get("employer", 0)), ("Cost to company", t.get("ctc", 0))]
    for i, (k, v) in enumerate(rows, 4):
        a, b = ws.cell(i, 1, k), ws.cell(i, 2, v)
        a.font = X["Font"](bold=True, color="1E3A8A"); a.fill = X["Fill"]("solid", fgColor="EFF6FF"); a.border = X["B"]; b.border = X["B"]
        if isinstance(v, float) or k in ("Gross earnings", "Total deductions", "NET PAYABLE", "Employer contributions", "Cost to company"):
            b.number_format = INR
    ws.column_dimensions["A"].width = 34; ws.column_dimensions["B"].width = 24

    # Register
    ecodes, dcodes, ercodes = [], [], []
    names = {}
    for l in lines:
        for e in l.earnings or []:
            if e["code"] not in ecodes:
                ecodes.append(e["code"]); names[e["code"]] = e["name"]
        for d in l.deductions or []:
            if d["code"] not in dcodes:
                dcodes.append(d["code"]); names[d["code"]] = d["name"]
        for e in l.employer or []:
            if e["code"] not in ercodes:
                ercodes.append(e["code"]); names[e["code"]] = e["name"]
    hd = (["Emp ID", "Name", "Designation", "Location", "Monthly gross", "Days", "Paid days", "LOP"]
          + [names[c] for c in ecodes] + ["GROSS EARNED"] + [names[c] for c in dcodes] + ["TOTAL DEDUCTIONS", "NET PAY"]
          + [names[c] for c in ercodes] + ["Bank", "Account", "IFSC", "Mode", "Status", "Note"])
    ws = wb.create_sheet("Salary Register")
    _banner(ws, f"Salary Register — {period_label(run.period)}", "All employees in this run (excluded rows greyed, net 0)", len(hd), X)
    for j, h in enumerate(hd, 1):
        c = ws.cell(4, j, h)
        for k, v in X["head"].items():
            setattr(c, k, v)
        c.border = X["B"]
    ws.row_dimensions[4].height = 34
    money_cols = set()
    r = 5
    for l in lines:
        s = l.snapshot or {}; a = l.attendance or {}
        em = {e["code"]: e["amount"] for e in l.earnings or []}
        dm = {}
        for d in l.deductions or []:
            dm[d["code"]] = dm.get(d["code"], 0) + d["amount"]
        erm = {e["code"]: e["amount"] for e in l.employer or []}
        status = "Excluded: " + (l.exclude_reason or "") if not l.included else ("On hold" if l.hold else l.pay_status.capitalize())
        row = ([s.get("emp_code"), s.get("name"), s.get("designation"), s.get("location"), s.get("monthly_gross"),
                a.get("cycle_days"), a.get("paid_days_final", a.get("paid_days")), a.get("lop")]
               + [em.get(c, 0) for c in ecodes] + [float(l.gross)] + [dm.get(c, 0) for c in dcodes]
               + [float(l.total_deductions), float(l.net) if l.included else 0] + [erm.get(c, 0) for c in ercodes]
               + [s.get("bank_name"), s.get("account_masked"), s.get("ifsc"), s.get("payment_mode"), status, l.utr or ""])
        for j, v in enumerate(row, 1):
            c = ws.cell(r, j, v); c.border = X["B"]
            if j == 5 or 9 <= j <= 8 + len(ecodes) + 1 + len(dcodes) + 2 + len(ercodes):
                c.number_format = INR; money_cols.add(j)
            if not l.included:
                c.font = X["Font"](color="94A3B8", italic=True)
            elif hd[j - 1] == "NET PAY":
                c.font = X["Font"](bold=True, color="166534")
        r += 1
    tr = r
    ws.cell(tr, 1, "TOTAL").font = X["Font"](bold=True)
    for j in sorted(money_cols):
        if j == 5:
            continue
        L = get_column_letter(j)
        c = ws.cell(tr, j, f"=SUM({L}5:{L}{tr - 1})"); c.number_format = INR; c.font = X["Font"](bold=True, color="1E3A8A")
        c.fill = X["Fill"]("solid", fgColor="EFF6FF")
    widths = [10, 24, 16, 14, 13, 6, 9, 6] + [13] * (len(ecodes) + 1 + len(dcodes) + 2 + len(ercodes)) + [18, 18, 13, 8, 18, 18]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "C5"
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


# ───────────────────────────────────────────────────────────── bank file (template-driven)
BANK_FIELDS = {
    "serial": "Serial no.", "payment_mode": "Payment mode (mapped codes)", "amount": "Amount (net pay)",
    "value_date": "Value / pay date", "debit_account": "Company debit account", "beneficiary_name": "Beneficiary name",
    "beneficiary_account": "Beneficiary account no.", "ifsc": "IFSC", "bank_name": "Beneficiary bank",
    "emp_code": "Employee ID", "employee_name": "Employee name", "email": "Email", "phone": "Mobile",
    "narration": "Narration / remarks", "customer_ref": "Customer reference", "period": "Salary month",
    "constant": "Fixed text (value)", "blank": "Blank",
}


def guess_field(header: str) -> str:
    h = re.sub(r"[^a-z]", "", (header or "").lower())
    rules = [("ifsc", "ifsc"), ("debit", "debit_account"), ("corporate", "debit_account"), ("amount", "amount"), ("amt", "amount"),
             ("valuedate", "value_date"), ("date", "value_date"), ("paymentmode", "payment_mode"), ("paytype", "payment_mode"),
             ("txntype", "payment_mode"), ("transactiontype", "payment_mode"), ("mode", "payment_mode"),
             ("beneficiaryaccount", "beneficiary_account"), ("beneaccount", "beneficiary_account"), ("benefaccount", "beneficiary_account"),
             ("accountno", "beneficiary_account"), ("accountnumber", "beneficiary_account"),
             ("beneficiaryname", "beneficiary_name"), ("benename", "beneficiary_name"), ("name", "beneficiary_name"),
             ("bankname", "bank_name"), ("bank", "bank_name"), ("email", "email"), ("mobile", "phone"), ("phone", "phone"),
             ("narration", "narration"), ("remark", "narration"), ("purpose", "narration"),
             ("reference", "customer_ref"), ("refno", "customer_ref"), ("crn", "customer_ref"), ("empid", "emp_code"),
             ("employee", "emp_code"), ("srno", "serial"), ("slno", "serial"), ("serial", "serial")]
    for key, f in rules:
        if key in h:
            return f
    return "blank"


def parse_bank_sample(content: bytes, filename: str) -> dict:
    """Read a bank's sample upload file → its header row + 3 sample rows + a guessed mapping."""
    rows = []
    if filename.lower().endswith((".csv", ".txt")):
        text = content.decode("utf-8-sig", errors="replace")
        delim = max([",", "|", "\t", ";", "^"], key=lambda d: text.splitlines()[0].count(d) if text else 0)
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
        ftype = "csv" if delim == "," else "txt"
    else:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        for r in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else str(v) for v in r])
            if len(rows) > 60:
                break
        delim, ftype = ",", "xlsx"
    hi = next((i for i, r in enumerate(rows) if sum(1 for v in r if str(v).strip()) >= 3), 0)
    header = [str(v).strip() for v in (rows[hi] if rows else [])]
    while header and not header[-1]:
        header.pop()
    samples = [r[:len(header)] for r in rows[hi + 1:hi + 4]]
    return {"file_type": ftype, "delimiter": delim, "headers": header, "samples": samples,
            "columns": [{"header": h, "field": guess_field(h), "value": ""} for h in header]}


def bank_rows(template, run, lines, cfg) -> list[list]:
    opt = template.options or {}
    same = (opt.get("same_bank_ifsc") or "").upper().strip()
    dfmt = opt.get("date_format") or "%d-%m-%Y"
    narr = opt.get("narration") or "SALARY {MONTH} {CODE}"
    out = []
    n = 0
    for l in lines:
        if not l.included or l.hold or float(l.net or 0) <= 0:
            continue
        s = l.snapshot or {}
        if (s.get("payment_mode") or "bank") != "bank":
            continue
        n += 1
        ifsc = (s.get("ifsc") or "").upper()
        mode = (opt.get("mode_same_bank") or "I") if same and ifsc.startswith(same) else (opt.get("mode_other") or "N")
        vals = {
            "serial": n, "payment_mode": mode, "amount": float(l.net),
            "value_date": (run.pay_date or date.today()).strftime(dfmt), "debit_account": opt.get("debit_account") or "",
            "beneficiary_name": (s.get("holder") or s.get("name") or "")[:int(opt.get("name_max") or 60)],
            "beneficiary_account": s.get("_account") or "", "ifsc": ifsc, "bank_name": s.get("bank_name") or "",
            "emp_code": s.get("emp_code") or "", "employee_name": s.get("name") or "", "email": s.get("email") or "",
            "phone": s.get("phone") or "", "customer_ref": f"PR{run.id}{s.get('emp_code') or l.user_id}"[:20],
            "period": period_label(run.period),
            "narration": narr.replace("{MONTH}", period_label(run.period)).replace("{CODE}", str(s.get("emp_code") or ""))
                         .replace("{NAME}", s.get("name") or "")[:int(opt.get("narration_max") or 30)],
        }
        row = []
        for c in template.columns or []:
            f = c.get("field")
            row.append((c.get("value") or "") if f == "constant" else ("" if f == "blank" else vals.get(f, "")))
        out.append(row)
    return out


def bank_file(template, run, lines, cfg) -> tuple[bytes, str, str]:
    rows = bank_rows(template, run, lines, cfg)
    headers = [c.get("header") or "" for c in template.columns or []]
    amount_idx = [i for i, c in enumerate(template.columns or []) if c.get("field") == "amount"]
    acct_idx = [i for i, c in enumerate(template.columns or []) if c.get("field") in ("beneficiary_account", "debit_account")]
    base = re.sub(r"[^A-Za-z0-9]+", "_", f"{template.bank or template.name}_SALARY_{run.period}")
    if (template.file_type or "xlsx") == "xlsx":
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "Salary"
        r0 = 1
        if template.include_header:
            ws.append(headers); r0 = 2
        for row in rows:
            ws.append(row)
        for r in range(r0, ws.max_row + 1):
            for i in acct_idx:
                c = ws.cell(r, i + 1); c.number_format = "@"; c.value = str(c.value or "")
            for i in amount_idx:
                ws.cell(r, i + 1).number_format = "0.00"
        for i, h in enumerate(headers, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(40, len(h) + 4))
        out = io.BytesIO(); wb.save(out)
        return out.getvalue(), base + ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    delim = template.delimiter or ","
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim[0] if len(delim) == 1 else ",", lineterminator="\r\n")
    if template.include_header:
        w.writerow(headers)
    for row in rows:
        w.writerow([("%.2f" % v) if i in amount_idx and isinstance(v, float) else v for i, v in enumerate(row)])
    text = buf.getvalue()
    if len(delim) > 1:
        text = text.replace(",", delim)
    ext = "csv" if template.file_type == "csv" else "txt"
    return text.encode("utf-8"), f"{base}.{ext}", "text/plain"


# ───────────────────────────────────────────────────────────── statutory files
def pf_ecr(run, lines) -> bytes:
    """EPFO ECR text: UAN#~#Name#~#Gross#~#EPF wages#~#EPS wages#~#EDLI wages#~#EE#~#EPS#~#ER diff#~#NCP days#~#Refund."""
    out = []
    for l in lines:
        if not l.included:
            continue
        s = l.snapshot or {}; w = (l.attendance or {}).get("statutory_wages") or {}
        ee = sum(d["amount"] for d in l.deductions or [] if d["code"] == "PF")
        if not ee:
            continue
        eps = sum(e["amount"] for e in l.employer or [] if e["code"] == "PF_EPS")
        diff = sum(e["amount"] for e in l.employer or [] if e["code"] == "PF_EPF")
        ncp = round(float((l.attendance or {}).get("lop") or 0))
        out.append("#~#".join(str(x) for x in [s.get("uan") or "", (s.get("name") or "").upper(), round(float(l.gross)),
                                                round(w.get("pf_wage", 0)), round(w.get("eps_wage", 0)), round(w.get("edli_wage", 0)),
                                                round(ee), round(eps), round(diff), ncp, 0]))
    return ("\n".join(out) + "\n").encode("utf-8")


def statutory_xlsx(run, lines, cfg) -> bytes:
    from openpyxl import Workbook
    X = _xl_styles()
    wb = Workbook()
    INR = '₹ #,##0.00'

    def sheet(ws, title, hd, data):
        _banner(ws, f"{title} — {period_label(run.period)}", f"Cycle {_d(run.cycle_start)} to {_d(run.cycle_end)}", len(hd), X)
        for j, h in enumerate(hd, 1):
            c = ws.cell(4, j, h)
            for k, v in X["head"].items():
                setattr(c, k, v)
        for i, row in enumerate(data, 5):
            for j, v in enumerate(row, 1):
                c = ws.cell(i, j, v); c.border = X["B"]
                if isinstance(v, float):
                    c.number_format = INR
        for j in range(1, len(hd) + 1):
            ws.column_dimensions[ws.cell(4, j).column_letter].width = 16
        ws.column_dimensions["B"].width = 26

    inc = [l for l in lines if l.included]
    pfrows, esirows, ptrows = [], [], []
    for l in inc:
        s = l.snapshot or {}; w = (l.attendance or {}).get("statutory_wages") or {}
        dm = {}
        for d in l.deductions or []:
            dm[d["code"]] = dm.get(d["code"], 0) + d["amount"]
        em = {e["code"]: e["amount"] for e in l.employer or []}
        if dm.get("PF"):
            pfrows.append([s.get("emp_code"), s.get("name"), s.get("uan") or "", float(w.get("pf_wage", 0)), float(dm["PF"]),
                           float(em.get("PF_EPS", 0)), float(em.get("PF_EPF", 0)), round(float((l.attendance or {}).get("lop") or 0))])
        if dm.get("ESI"):
            esirows.append([s.get("emp_code"), s.get("name"), s.get("esic_number") or "", (l.attendance or {}).get("paid_days_final"),
                            float(w.get("esi_wage", 0)), float(dm["ESI"]), float(em.get("ESI_ER", 0))])
        if dm.get("PT"):
            ptrows.append([s.get("emp_code"), s.get("name"), float(w.get("pt_wage", 0)), float(dm["PT"])])
    ws = wb.active; ws.title = "PF"
    sheet(ws, "Provident Fund", ["Emp ID", "Name", "UAN", "PF wages", "Employee PF", "Employer EPS", "Employer EPF", "NCP days"], pfrows)
    sheet(wb.create_sheet("ESI"), "ESI", ["Emp ID", "Name", "ESIC no.", "Paid days", "ESI wages", "Employee ESI", "Employer ESI"], esirows)
    sheet(wb.create_sheet("Professional Tax"), f"Professional Tax ({((cfg.get('statutory') or {}).get('pt') or {}).get('state', '')})",
          ["Emp ID", "Name", "PT wages", "PT"], ptrows)
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


# ───────────────────────────────────────────────────────────── annual tax statement (Form 16 Part B layout)
def _pdf():
    from fpdf import FPDF
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(True, 15)
    pdf.add_font("dv", "", FONT)
    pdf.add_font("dv", "B", FONT_B)
    return pdf


def _head(pdf, cfg, title, sub):
    co = cfg.get("company") or {}
    NAVY = _hex((cfg.get("payslip") or {}).get("accent"))
    pdf.set_fill_color(*NAVY); pdf.rect(0, 0, 210, 28, "F")
    logo = _logo_file(cfg); x0 = 12
    if logo:
        try:
            pdf.image(logo, 12, 5, h=18); x0 = 36
        except Exception:
            pass
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(x0, 7); pdf.set_font("dv", "B", 13); pdf.cell(110, 6, (co.get("name") or "")[:50])
    pdf.set_xy(x0, 14); pdf.set_font("dv", "", 7); pdf.multi_cell(105, 3.4, (co.get("address") or "")[:200], align="L")
    pdf.set_xy(120, 7); pdf.set_font("dv", "B", 11); pdf.cell(80, 6, title, align="R")
    pdf.set_xy(120, 14); pdf.set_font("dv", "", 8); pdf.cell(80, 5, sub, align="R")
    pdf.set_text_color(15, 23, 42); pdf.set_y(34)
    return NAVY


def _kv_table(pdf, rows, NAVY, title=None, col=(120, 70)):
    if title:
        pdf.set_font("dv", "B", 9); pdf.set_fill_color(*NAVY); pdf.set_text_color(255, 255, 255)
        pdf.cell(sum(col), 7, "  " + title, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(15, 23, 42)
    pdf.set_font("dv", "", 8.6)
    for i, (k, v, bold) in enumerate(rows):
        pdf.set_fill_color(*((248, 250, 252) if i % 2 else (255, 255, 255)))
        pdf.set_font("dv", "B" if bold else "", 8.6)
        pdf.cell(col[0], 6.4, "  " + str(k), fill=True)
        pdf.cell(col[1], 6.4, v if isinstance(v, str) else money(v), fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def form16_pdf(items: list[dict], cfg: dict) -> bytes:
    """items = [{employee:{…}, fy, months:[{label, gross, tds, pay_date}], tax:{…annual dict…}, regime, provisional}]"""
    pdf = _pdf()
    co = cfg.get("company") or {}
    for it in items:
        pdf.add_page()
        e = it["employee"]; t = it["tax"]
        NAVY = _head(pdf, cfg, "ANNUAL TAX STATEMENT", f"FY {it['fy']} · Form 16 Part B layout")
        pdf.set_font("dv", "", 8.4)
        info = [("Employer", co.get("name") or "—"), ("Employer TAN / PAN", f"{co.get('tan') or '—'} / {co.get('pan') or '—'}"),
                ("Employee", f"{e.get('name')} ({e.get('emp_code') or '—'})"), ("Employee PAN", e.get("pan") or "NOT GIVEN"),
                ("Designation", e.get("designation") or "—"), ("Tax regime", "New regime (115BAC)" if it["regime"] == "new" else "Old regime")]
        for i, (k, v) in enumerate(info):
            pdf.set_xy(12 + (i % 2) * 95, 36 + (i // 2) * 9)
            pdf.set_font("dv", "", 6.8); pdf.set_text_color(100, 116, 139); pdf.cell(90, 3.4, k.upper())
            pdf.set_xy(12 + (i % 2) * 95, 39.6 + (i // 2) * 9); pdf.set_font("dv", "B", 9); pdf.set_text_color(15, 23, 42); pdf.cell(90, 4.5, str(v)[:48])
        pdf.set_xy(10, 66)
        if it.get("provisional"):
            pdf.set_text_color(180, 83, 9); pdf.set_font("dv", "B", 8)
            pdf.cell(190, 5, "PROVISIONAL — year not complete. Tax is projected for the full year (the basis of your monthly TDS).",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(15, 23, 42)
        rows = [("1. Gross salary (this employer)" + (" — projected" if it.get("provisional") else ""), t["gross"] - (it.get("prev_income") or 0), False),
                ("    Salary from previous employer (declared)", it.get("prev_income") or 0, False),
                ("2. Less: exemption u/s 10 (HRA)", t["hra_exempt"], False),
                ("3. Less: standard deduction u/s 16(ia)", t["std_deduction"], False),
                ("4. Less: professional tax u/s 16(iii)", t["professional_tax"], False),
                ("5. Less: interest on housing loan u/s 24(b)", t["house_loss"], False),
                ("6. Add: other income declared", t["other_income"], False)]
        _kv_table(pdf, rows, NAVY, "Income from salary")
        via = [(f"    {x['name']}", x["amount"], False) for x in t.get("chapter_via") or []]
        _kv_table(pdf, via + [("7. Total deductions under Chapter VI-A", t["deductions"], True)], NAVY, "Deductions (Chapter VI-A)")
        _kv_table(pdf, [("8. Total taxable income", t["taxable"], True), ("9. Tax on total income", t["slab_tax"], False),
                        ("10. Less: rebate u/s 87A (incl. marginal relief)", t["rebate"], False), ("11. Surcharge", t["surcharge"], False),
                        ("12. Health & education cess", t["cess"], False), ("13. Tax payable (rounded to ₹10)", t["total"], True),
                        ("14. Tax deducted by previous employer", t.get("prev_employer_tds") or 0, False),
                        ("15. Tax deducted by this employer (TDS)", it["tds_total"], True),
                        ("16. Balance tax payable / (refundable)", t["total"] - (t.get("prev_employer_tds") or 0) - it["tds_total"], True)],
                  NAVY, "Tax computation")
        pdf.set_font("dv", "B", 9); pdf.set_fill_color(*NAVY); pdf.set_text_color(255, 255, 255)
        for w, h in ((50, "Month"), (55, "Salary paid"), (45, "TDS deducted"), (40, "Pay date")):
            pdf.cell(w, 7, " " + h, fill=True)
        pdf.ln(); pdf.set_text_color(15, 23, 42); pdf.set_font("dv", "", 8.4)
        for i, m in enumerate(it["months"]):
            pdf.set_fill_color(*((248, 250, 252) if i % 2 else (255, 255, 255)))
            pdf.cell(50, 6, " " + m["label"], fill=True); pdf.cell(55, 6, money(m["gross"]) + " ", fill=True, align="R")
            pdf.cell(45, 6, money(m["tds"]) + " ", fill=True, align="R"); pdf.cell(40, 6, " " + (m.get("pay_date") or "—"), fill=True)
            pdf.ln()
        pdf.ln(4); pdf.set_font("dv", "", 7); pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(190, 3.6, "Statement generated by the employer's payroll from approved salary runs and the employee's declarations. "
                                  "Part A (TDS deposited, challan details) is issued from the TRACES portal. Verify before filing your return.")
    return bytes(pdf.output())


def tds_24q_xlsx(rows: list[list], fy: str, quarter: str) -> bytes:
    from openpyxl import Workbook
    X = _xl_styles()
    wb = Workbook(); ws = wb.active; ws.title = "Deductee details"
    hd = ["Month", "Emp ID", "Employee name", "PAN", "Section", "Date of payment", "Amount paid / credited", "TDS deducted", "Regime"]
    _banner(ws, f"TDS on salary (24Q) — FY {fy} {quarter}", "Deductee-wise salary and TDS from approved payroll runs. Deposit date / challan from your bank.", len(hd), X)
    for j, h in enumerate(hd, 1):
        c = ws.cell(4, j, h)
        for k, v in X["head"].items():
            setattr(c, k, v)
    for i, r_ in enumerate(rows, 5):
        for j, v in enumerate(r_, 1):
            c = ws.cell(i, j, v); c.border = X["B"]
            if j in (7, 8):
                c.number_format = '₹ #,##0.00'
    for j, w in enumerate([10, 10, 26, 13, 9, 14, 18, 14, 8], 1):
        ws.column_dimensions[ws.cell(4, j).column_letter].width = w
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


# ───────────────────────────────────────────────────────────── full & final settlement letter
def fnf_pdf(f, emp: dict, cfg: dict) -> bytes:
    pdf = _pdf(); pdf.add_page()
    NAVY = _head(pdf, cfg, "FULL & FINAL SETTLEMENT", f"Last working day {_d(f.last_working_day)}")
    info = [("Employee", f"{emp.get('name')} ({emp.get('emp_code') or '—'})"), ("Designation", emp.get("designation") or "—"),
            ("Date of joining", emp.get("joining_date") or "—"), ("Reason for leaving", (f.reason or "—").capitalize()),
            ("PAN", emp.get("pan") or "—"), ("Bank", f"{emp.get('bank_name') or '—'} {emp.get('account_masked') or ''}")]
    for i, (k, v) in enumerate(info):
        pdf.set_xy(12 + (i % 2) * 95, 36 + (i // 2) * 9)
        pdf.set_font("dv", "", 6.8); pdf.set_text_color(100, 116, 139); pdf.cell(90, 3.4, k.upper())
        pdf.set_xy(12 + (i % 2) * 95, 39.6 + (i // 2) * 9); pdf.set_font("dv", "B", 9); pdf.set_text_color(15, 23, 42); pdf.cell(90, 4.5, str(v)[:48])
    pdf.set_xy(10, 66)
    earn = [(i["name"] + (f" — {i['note']}" if i.get("note") else ""), float(i["amount"]), False) for i in f.items or [] if i["kind"] == "earning"]
    ded = [(i["name"] + (f" — {i['note']}" if i.get("note") else ""), float(i["amount"]), False) for i in f.items or [] if i["kind"] == "deduction"]
    _kv_table(pdf, earn + [("Total payable to employee", float(f.total_earnings), True)], NAVY, "Earnings / dues")
    _kv_table(pdf, ded + [("Total recoveries", float(f.total_deductions), True)], NAVY, "Deductions / recoveries")
    net = float(f.net)
    pdf.set_fill_color(*((22, 101, 52) if net >= 0 else (185, 28, 28))); pdf.set_text_color(255, 255, 255)
    pdf.set_font("dv", "B", 12)
    pdf.cell(190, 12, ("  NET PAYABLE TO EMPLOYEE  " if net >= 0 else "  AMOUNT RECOVERABLE FROM EMPLOYEE  ") + money(abs(net)), fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(15, 23, 42); pdf.set_font("dv", "", 8); pdf.ln(2)
    pdf.multi_cell(190, 4.2, words_inr(abs(net)))
    pdf.ln(3)
    status = {"draft": "DRAFT — not approved", "approved": "Approved", "paid": f"Paid on {_d(f.paid_on)}" + (f" · UTR {f.utr}" if f.utr else "")}.get(f.status, f.status)
    pdf.set_font("dv", "B", 8.5); pdf.cell(190, 5, f"Status: {status}", new_x="LMARGIN", new_y="NEXT")
    if f.note:
        pdf.set_font("dv", "", 8); pdf.multi_cell(190, 4, "Note: " + f.note[:600])
    pdf.ln(14); pdf.set_font("dv", "", 8.5)
    pdf.cell(95, 5, "Employee signature"); pdf.cell(95, 5, f"For {(cfg.get('company') or {}).get('name') or ''}"[:50], align="R",
                                                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 7); pdf.set_text_color(100, 116, 139); pdf.ln(4)
    pdf.multi_cell(190, 3.5, "I confirm I have received the above amount in full and final settlement of all my dues and have no further claim on the company.")
    return bytes(pdf.output())
