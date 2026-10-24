"""Portfolio download — one styled Excel workbook for a whole portfolio (bank + product), optionally one
location, with EVERY case and its CURRENT status. Built for the Accounts / Portfolio section.

Sheets:
  1. Summary   — headline KPIs, status breakdown, location split, FOS split.
  2. All cases — every case, colour-coded status, frozen header, filters, totals row.
"""
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import models

_IST = timezone(timedelta(hours=5, minutes=30))

NAVY, BLUE, LIGHT, GRID = "0B2545", "1D4ED8", "EEF4FF", "D6DEEB"
STATUS_FILL = {
    "PAID": ("DCFCE7", "166534"), "PARTIAL": ("FEF3C7", "92400E"), "UNPAID": ("FEE2E2", "991B1B"),
}
DISPO_FILL = {"PTP": ("DBEAFE", "1E40AF"), "RTP": ("FEE2E2", "991B1B"), "PAID": ("DCFCE7", "166534")}


def _n(v) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _d(v):
    if not v:
        return ""
    try:
        if isinstance(v, datetime):
            return (v.astimezone(_IST) if v.tzinfo else v).strftime("%d-%b-%Y %H:%M")
        return v.strftime("%d-%b-%Y")
    except Exception:
        return str(v)


def _people(db, ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.query(models.User.id, models.User.name, models.User.emp_code).filter(models.User.id.in_(ids)).all()
    return {i: (f"{n or ''} ({e})" if e else (n or "")) for i, n, e in rows}


def _last_visits(db, case_ids):
    from sqlalchemy import func
    out = {}
    ids = list(case_ids)
    for k in range(0, len(ids), 900):
        chunk = ids[k:k + 900]
        for cid, at, cnt in (db.query(models.Visit.case_id, func.max(models.Visit.created_at), func.count(models.Visit.id))
                             .filter(models.Visit.case_id.in_(chunk)).group_by(models.Visit.case_id).all()):
            out[cid] = (at, cnt)
    return out


def build(db, cases, title: str, subtitle: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from . import paymath

    today = datetime.now(_IST).date()
    names = _people(db, [c.assigned_fos_id for c in cases] + [c.assigned_caller_id for c in cases]
                    + [c.joint_fos_id for c in cases] + [c.esc_prev_fos_id for c in cases]
                    + [c.esc_prev_caller_id for c in cases] + [c.escalated_to for c in cases])
    visits = _last_visits(db, [c.id for c in cases])

    thin = Side(style="thin", color=GRID)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    hdr_fill = PatternFill("solid", fgColor=NAVY)
    fill = lambda c: PatternFill("solid", fgColor=c)
    money = '#,##0;[Red]-#,##0;"-"'

    # ── per-case rows ────────────────────────────────────────────────────────────────
    rows, stats = [], {"PAID": 0, "PARTIAL": 0, "UNPAID": 0}
    tot = dict(tos=0.0, enr=0.0, norm=0.0, stab=0.0, recv=0.0, pend=0.0, cash=0.0, part=0.0)
    by_loc, by_fos, by_dispo = {}, {}, {}
    for c in cases:
        ps = (c.paid_status or "UNPAID").upper()
        stats[ps] = stats.get(ps, 0) + 1
        try:
            cash = float(paymath.cash_qualified(c))
            part = float(paymath.partial_amount(c))
        except Exception:
            cash, part = (_n(c.received_amount), 0.0) if ps == "PAID" else (0.0, _n(c.received_amount))
        try:
            pn = paymath.remaining_to_norm(c)
            ps_ = paymath.remaining_to_stab(c)
        except Exception:
            pn = ps_ = None
        fos_id = c.assigned_fos_id or c.esc_prev_fos_id
        caller_id = c.assigned_caller_id or c.esc_prev_caller_id
        fos = names.get(fos_id) or (c.fos_name or "")
        caller = names.get(caller_id) or (c.caller_name or "")
        lv = visits.get(c.id)
        closed = bool(c.close_date and c.close_date < today)
        state = ("Escalated" if c.escalated else "Closed" if closed else
                 "Paid" if ps == "PAID" else "Partial" if ps == "PARTIAL" else
                 "PTP" if (c.disposition or "").upper() == "PTP" else
                 "Worked" if (c.last_contacted_at or lv) else "Not worked")
        loc = c.branch or "—"
        L = by_loc.setdefault(loc, [0, 0, 0.0, 0.0]); L[0] += 1; L[1] += ps == "PAID"; L[2] += _n(c.received_amount); L[3] += _n(c.pending_amount)
        F = by_fos.setdefault(fos or "Unallocated", [0, 0, 0, 0.0]); F[0] += 1; F[1] += ps == "PAID"; F[2] += ps == "PARTIAL"; F[3] += _n(c.received_amount)
        dk = (c.disposition or "No disposition").upper()
        by_dispo[dk] = by_dispo.get(dk, 0) + 1
        for k, v in (("tos", c.total_outstanding), ("enr", c.enr), ("norm", c.norm_amount), ("stab", c.stab_amount),
                     ("recv", c.received_amount), ("pend", c.pending_amount)):
            tot[k] += _n(v)
        tot["cash"] += cash; tot["part"] += part
        rows.append([
            c.id, c.account_no or "", c.card_no or "", c.customer_name or "", c.phone or "", c.alt_phone or "",
            c.new_phone or "", c.bank or "", c.product or "", loc, c.bucket or "", c.cycle or "", c.period or "",
            _d(c.close_date), state, ps, c.norm_stab or "", c.disposition or "",
            _d(c.follow_up_date) if (c.disposition or "").upper() == "PTP" else "",
            _n(c.total_outstanding), _n(c.enr), _n(c.norm_amount), _n(c.stab_amount),
            _n(c.received_amount), cash, part, _n(c.pending_amount),
            _n(pn) if pn is not None else "", _n(ps_) if ps_ is not None else "",
            fos, caller, c.team_lead or "", names.get(c.joint_fos_id, ""),
            _d(c.last_contacted_at), _d(lv[0]) if lv else "", lv[1] if lv else 0,
            "Yes" if c.flagged else "", (c.remarks or "")[:300],
            c.address or "", c.address2 or "", c.address3 or "", c.new_address or "", c.pincode or "",
        ])

    # ── house style (same as the Attendance + Team/Employee reports) ──────────────────
    from openpyxl.formatting.rule import DataBarRule
    NAVY_T, BLUE_H, ZEBRA_C, TOT_C = "0F2747", "1D4ED8", "F7F9FC", "DCE6FA"
    GOOD_C, MID_C, BAD_C = "C6EFCE", "FFEB9C", "FFC7CE"
    TITLE_FONT = Font(bold=True, size=15, color=NAVY_T)
    SUB_FONT = Font(size=10, color="5B6B82")
    HEAD_FONT = Font(bold=True, color="FFFFFF", size=10.5)
    side = Side(style="thin", color="D6DEEA")
    BORDER = Border(left=side, right=side, top=side, bottom=side)
    CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
    LEFT1 = Alignment(horizontal="left", vertical="center", wrap_text=False)
    RUPEE = '"₹"#,##0'
    STATE_C = {"Paid": (GOOD_C, "166534"), "Partial": (MID_C, "92400E"), "PTP": ("BDD7EE", "1E40AF"),
               "Not worked": (BAD_C, "B91C1C"), "Worked": ("E2E8F0", "334155"),
               "Closed": ("E2E8F0", "64748B"), "Escalated": ("DDD6FE", "5B21B6")}
    PAID_C = {"PAID": (GOOD_C, "166534"), "PARTIAL": (MID_C, "92400E"), "UNPAID": (BAD_C, "B91C1C")}
    DISPO_C = {"PTP": ("BDD7EE", "1E40AF"), "RTP": (BAD_C, "B91C1C"), "PAID": (GOOD_C, "166534")}

    def title_block(ws, ncols):
        ws.append([title]); ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        ws["A1"].font = TITLE_FONT; ws.row_dimensions[1].height = 26
        ws.append([subtitle]); ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
        ws["A2"].font = SUB_FONT
        ws.append([])

    def head(ws, r, c, text, color=BLUE_H):
        cell = ws.cell(row=r, column=c, value=text)
        cell.fill, cell.font, cell.alignment, cell.border = fill(color), HEAD_FONT, CENTER, BORDER
        return cell

    def pill(cell, pal, key):
        if key in pal:
            bg, fg = pal[key]
            cell.fill = fill(bg); cell.font = Font(bold=True, size=9.5, color=fg)

    def tint(cell, v):
        cell.fill = fill(GOOD_C if v >= 0.6 else MID_C if v >= 0.3 else BAD_C)

    wb = Workbook()
    n = len(cases)
    actual = tot["cash"] + tot["part"]

    # ── Sheet 1: Summary ─────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    title_block(ws, 6)
    for col, w in zip("ABCDEF", (30, 15, 15, 17, 17, 17)):
        ws.column_dimensions[col].width = w

    # KPI tiles: 3 per row, label band on top, big value below
    kpis = [("Total cases", n, "#,##0", BLUE_H), ("Paid", stats.get("PAID", 0), "#,##0", "15803D"),
            ("Partial", stats.get("PARTIAL", 0), "#,##0", "B45309"), ("Unpaid", stats.get("UNPAID", 0), "#,##0", "B91C1C"),
            ("Paid %", (stats.get("PAID", 0) / n) if n else 0, "0.0%", "0F766E"), ("TOS", tot["tos"], RUPEE, NAVY_T),
            ("ENR", tot["enr"], RUPEE, NAVY_T), ("Received", tot["recv"], RUPEE, "15803D"),
            ("Pending", tot["pend"], RUPEE, "B45309"), ("Cash collection", tot["cash"], RUPEE, "0369A1"),
            ("Partial payments", tot["part"], RUPEE, "7C3AED"), ("Actual collection (cash + partial)", actual, RUPEE, "15803D")]
    r = 4
    for i in range(0, len(kpis), 3):
        for j, (lbl, val, fmt, color) in enumerate(kpis[i:i + 3]):
            col = 1 + j * 2
            ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + 1)
            ws.merge_cells(start_row=r + 1, start_column=col, end_row=r + 1, end_column=col + 1)
            a = ws.cell(r, col, lbl); a.fill = fill(color); a.font = Font(bold=True, size=9.5, color="FFFFFF"); a.alignment = CENTER
            v = ws.cell(r + 1, col, val); v.number_format = fmt; v.alignment = CENTER
            v.font = Font(bold=True, size=16, color=color); v.fill = fill("EEF3FF")
            for cc in (col, col + 1):
                ws.cell(r, cc).border = BORDER; ws.cell(r + 1, cc).border = BORDER
        ws.row_dimensions[r].height = 18; ws.row_dimensions[r + 1].height = 32
        r += 3

    def table(r, heading, band_color, headers, data, fmts, total=None, pct_col=None, bar_col=None):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        b = ws.cell(r, 1, heading); b.fill = fill(band_color); b.font = HEAD_FONT; b.alignment = LEFT
        for j in range(1, len(headers) + 1):
            ws.cell(r, j).fill = fill(band_color)
        ws.row_dimensions[r].height = 20
        r += 1
        for j, h in enumerate(headers, 1):
            head(ws, r, j, h)
        ws.row_dimensions[r].height = 22
        first = r + 1
        for k, row in enumerate(data):
            r += 1
            for j, v in enumerate(row, 1):
                c = ws.cell(r, j, v); c.border = BORDER
                c.alignment = LEFT if j == 1 else CENTER
                if fmts[j - 1]:
                    c.number_format = fmts[j - 1]
                if k % 2:
                    c.fill = fill(ZEBRA_C)
            if j and pct_col:
                tint(ws.cell(r, pct_col), ws.cell(r, pct_col).value or 0)
        last = r
        if total:
            r += 1
            for j, v in enumerate(total, 1):
                c = ws.cell(r, j, v); c.fill = fill(TOT_C); c.font = Font(bold=True); c.border = BORDER
                c.alignment = LEFT if j == 1 else CENTER
                if fmts[j - 1]:
                    c.number_format = fmts[j - 1]
        if bar_col and last >= first:
            L = get_column_letter(bar_col)
            ws.conditional_formatting.add(f"{L}{first}:{L}{last}", DataBarRule(start_type="num", start_value=0, end_type="max", color="7DA2F0"))
        return r + 2

    r = table(r, "Status breakdown", "0F2747", ["Paid status", "Cases", "Share"],
              [[s_, stats.get(s_, 0), (stats.get(s_, 0) / n) if n else 0] for s_ in ("PAID", "PARTIAL", "UNPAID")],
              [None, "#,##0", "0.0%"], total=["TOTAL", n, 1 if n else 0], bar_col=2)
    locs = sorted(by_loc.items(), key=lambda x: -x[1][0])
    r = table(r, "By location", "0369A1", ["Location", "Cases", "Paid", "Paid %", "Received", "Pending"],
              [[k, v[0], v[1], (v[1] / v[0]) if v[0] else 0, v[2], v[3]] for k, v in locs],
              [None, "#,##0", "#,##0", "0.0%", RUPEE, RUPEE],
              total=["TOTAL", n, stats.get("PAID", 0), (stats.get("PAID", 0) / n) if n else 0, tot["recv"], tot["pend"]],
              pct_col=4, bar_col=2)
    fos_rows = sorted(by_fos.items(), key=lambda x: -x[1][0])
    r = table(r, "By FOS", "B45309", ["FOS", "Cases", "Paid", "Partial", "Paid %", "Received"],
              [[k, v[0], v[1], v[2], (v[1] / v[0]) if v[0] else 0, v[3]] for k, v in fos_rows],
              [None, "#,##0", "#,##0", "#,##0", "0.0%", RUPEE],
              total=["TOTAL", n, stats.get("PAID", 0), stats.get("PARTIAL", 0), (stats.get("PAID", 0) / n) if n else 0, tot["recv"]],
              pct_col=5, bar_col=2)
    r = table(r, "By disposition", "7C3AED", ["Disposition", "Cases", "Share"],
              [[k, v, (v / n) if n else 0] for k, v in sorted(by_dispo.items(), key=lambda x: -x[1])],
              [None, "#,##0", "0.0%"], total=["TOTAL", n, 1 if n else 0], bar_col=2)
    ws.page_setup.orientation = "portrait"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0

    # ── Sheet 2: All cases ───────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("All cases")
    GROUPS = [("Customer", NAVY_T, ["Case #", "Account", "Card", "Customer", "Phone", "Alt phone", "New phone"],
               [8, 18, 18, 26, 13, 13, 13]),
              ("Portfolio", "0369A1", ["Bank", "Product", "Location", "Bucket", "Cycle", "Month", "Close date"],
               [9, 12, 16, 10, 7, 9, 12]),
              ("Current status", "7C3AED", ["State", "Paid status", "N/S", "Disposition", "PTP date"],
               [12, 11, 7, 14, 12]),
              ("Amounts", "0F766E", ["TOS", "ENR", "NORM", "STAB", "Received", "Cash coll", "Partial", "Pending",
                                     "Pending NORM", "Pending STAB"], [12, 12, 11, 11, 12, 12, 11, 12, 12, 12]),
              ("Allocation & activity", "B45309", ["FOS", "Caller", "Team lead", "Joint FOS", "Last call",
                                                    "Last visit", "Visits", "Flag"], [24, 24, 13, 20, 17, 17, 7, 6]),
              ("Remarks & addresses", "475569", ["Remarks", "Address 1", "Address 2", "Address 3", "New address",
                                                  "Pincode"], [40, 45, 45, 45, 40, 9])]
    ncols = sum(len(g[2]) for g in GROUPS)
    title_block(ws2, min(ncols, 20))
    g_row, h_row = 4, 5
    col = 1
    for gname, gcolor, hdrs, widths in GROUPS:
        ws2.merge_cells(start_row=g_row, start_column=col, end_row=g_row, end_column=col + len(hdrs) - 1)
        for j, (h, w) in enumerate(zip(hdrs, widths)):
            c = ws2.cell(g_row, col + j); c.fill = fill(gcolor); c.border = BORDER
            head(ws2, h_row, col + j, h, gcolor)
            ws2.column_dimensions[get_column_letter(col + j)].width = w
        gc = ws2.cell(g_row, col, gname); gc.font = HEAD_FONT; gc.alignment = CENTER
        col += len(hdrs)
    ws2.row_dimensions[g_row].height = 20; ws2.row_dimensions[h_row].height = 30
    money_cols = set(range(20, 30))
    left_cols = {2, 3, 4, 10, 30, 31, 33} | set(range(38, 44))
    first = h_row + 1
    for i, row in enumerate(rows):
        rr = first + i
        zebra = fill(ZEBRA_C) if i % 2 else None
        for j, v in enumerate(row, 1):
            c = ws2.cell(rr, j, v); c.border = BORDER
            c.alignment = LEFT1 if j in left_cols else CENTER
            if j in money_cols:
                c.number_format = RUPEE
            if zebra:
                c.fill = zebra
        ws2.cell(rr, 4).font = Font(bold=True)
        pill(ws2.cell(rr, 15), STATE_C, row[14])
        pill(ws2.cell(rr, 16), PAID_C, row[15])
        pill(ws2.cell(rr, 18), DISPO_C, (row[17] or "").upper())
        if row[36]:
            pill(ws2.cell(rr, 37), {"Yes": (BAD_C, "B91C1C")}, "Yes")
        if row[23]:
            ws2.cell(rr, 24).font = Font(bold=True, color="166534")
        if row[26]:
            ws2.cell(rr, 27).font = Font(bold=True, color="9A3412")
    last = first + len(rows) - 1
    tr = last + 1
    for j in range(1, ncols + 1):
        c = ws2.cell(tr, j); c.fill = fill(TOT_C); c.font = Font(bold=True); c.border = BORDER; c.alignment = CENTER
    ws2.cell(tr, 1, "TOTAL").alignment = LEFT
    ws2.cell(tr, 4, f"{n} cases").alignment = LEFT
    for j in money_cols:
        L = get_column_letter(j)
        c = ws2.cell(tr, j, f"=SUBTOTAL(9,{L}{first}:{L}{last})" if rows else 0); c.number_format = RUPEE
    if rows:
        ws2.conditional_formatting.add(f"X{first}:X{last}", DataBarRule(start_type="num", start_value=0, end_type="max", color="63BE7B"))
        ws2.conditional_formatting.add(f"AA{first}:AA{last}", DataBarRule(start_type="num", start_value=0, end_type="max", color="F4B183"))
    ws2.freeze_panes = ws2.cell(row=first, column=5)
    ws2.auto_filter.ref = f"A{h_row}:{get_column_letter(ncols)}{max(last, h_row)}"
    ws2.print_title_rows = f"{g_row}:{h_row}"
    ws2.page_setup.orientation = "landscape"
    ws2.sheet_properties.pageSetUpPr.fitToPage = True
    ws2.page_setup.fitToWidth = 1; ws2.page_setup.fitToHeight = 0

    # ── Sheet 3: Legend ──────────────────────────────────────────────────────────────
    lg = wb.create_sheet("Legend")
    lg.append(["Colour", "Meaning"])
    for c in lg[1]:
        c.fill, c.font, c.border, c.alignment = fill(NAVY_T), HEAD_FONT, BORDER, CENTER
    for key, pal, meaning in [("Paid", STATE_C, "State — fully paid (NORM / STAB / full settlement)"),
                              ("Partial", STATE_C, "State — paid below the settlement amount"),
                              ("PTP", STATE_C, "State — customer promised to pay (date in PTP date)"),
                              ("Worked", STATE_C, "State — called or visited, no payment yet"),
                              ("Not worked", STATE_C, "State — no call or visit logged yet"),
                              ("Closed", STATE_C, "State — past its close date (cycle / month end)"),
                              ("Escalated", STATE_C, "State — pulled to head office / manager"),
                              ("RTP", DISPO_C, "Disposition — refused to pay")]:
        lg.append([key, meaning]); rr = lg.max_row
        pill(lg.cell(rr, 1), pal, key)
        for j in (1, 2):
            lg.cell(rr, j).border = BORDER
            lg.cell(rr, j).alignment = CENTER if j == 1 else LEFT
    lg.append([]); lg.append(["Cash coll", "Settled cash on PAID NORM/STAB cases (+ all money on plain cases)"])
    lg.append(["Partial", "Money received below the NORM/STAB settlement amount"])
    lg.append(["Actual coll", "Cash collection + partial payments"])
    lg.append(["Totals row", "Re-adds itself when you filter the All cases sheet"])
    for rr in range(lg.max_row - 3, lg.max_row + 1):
        lg.cell(rr, 1).font = Font(bold=True, color=NAVY_T)
    lg.column_dimensions["A"].width = 14; lg.column_dimensions["B"].width = 80

    wb.active = 0
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
