"""FOS field-visit reports generated straight from RecoverIQ data (Attendance section).

1. Daily FOS visit report  — GET /api/attendance/fos-report/daily.xlsx?start=&end=&branch=
   One sheet per day, same layout as the team's "TODAY FIELD VISIT REPORT": FOS, area, contact,
   reporting branch, first start time, total visits, productive (paid) visits, visits per time slot
   (8-11AM · 11-1PM morning / 1-4PM · 4-7PM evening), present status, remarks, start & end time.
   Plus a Summary sheet (per FOS across the range) and a branch summary on each day.

2. Monthly FOS visit & attendance sheet — GET /api/attendance/fos-report/monthly.xlsx?start=&end=&branch=
   The "SSD" attendance sheet for a salary cycle (21st → 20th): per FOS a visit count for every day
   (or a code: Sun / A / IN-A / NA), totals, average, working days, 0/1/2/3/4+ counts, Sundays,
   absents, leave, reasons, and a second block of PRODUCTIVE (PAID) counts per day.

Everything comes from check-ins (Attendance), visits (Visit: time, paid / amount collected), approved
leave and the employee's joining date / exit. Scope = whoever the viewer may see in Attendance.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date as date_cls, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import audit, models, presence
from ..database import get_db
from ..deps import get_current_user
from . import attendance as att

router = APIRouter(prefix="/api/attendance/fos-report", tags=["attendance"])
IST = presence.IST

SLOTS = [("8-11AM", 0, 11), ("11-1PM", 11, 13), ("1-4PM", 13, 16), ("4-7PM", 16, 24)]   # early visits fold into 8-11
NAVY, BLUE, GREEN, CYAN, YELLOW = "0F2747", "1D4ED8", "16A34A", "0EA5E9", "FDE68A"


# ---------------------------------------------------------------------------------------- data

def _parse_range(start: str | None, end: str | None, default_cycle: bool):
    today = att._ist_today()
    try:
        if start and end:
            a, b = date_cls.fromisoformat(start[:10]), date_cls.fromisoformat(end[:10])
        elif start:
            a = b = date_cls.fromisoformat(start[:10])
        elif default_cycle:                     # current salary cycle 21st → 20th
            b = date_cls(today.year, today.month, 20) if today.day <= 20 else \
                (date_cls(today.year + (today.month == 12), today.month % 12 + 1, 20))
            a = (date_cls(b.year - (b.month == 1), (b.month - 2) % 12 + 1, 21))
        else:
            a = b = today
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    if b < a:
        a, b = b, a
    if (b - a).days > 62:
        raise HTTPException(status_code=400, detail="Pick at most 2 months.")
    return a, b


def _is_fos(u: models.User) -> bool:
    return (u.role == "fos") or bool(getattr(u, "also_field_agent", False))


def _area(u: models.User) -> str:
    return (getattr(u, "location", None) or getattr(u, "branch", None) or "").strip()


def _ist(dt):
    return presence._aware(dt).astimezone(IST) if dt else None


def _t(dt) -> str:
    d = _ist(dt)
    return d.strftime("%I:%M%p").lstrip("0") if d else ""


def _collect(db: Session, viewer: models.User, a: date_cls, b: date_cls, branch: str | None):
    """→ (people, days, codes, visits) for every FOS the viewer may see.
    codes[uid][iso] = attendance code (P/L/H/H•/LV/W/A or '')
    visits[uid][iso] = {n, paid, slots[4], first, last}"""
    sheet = att.month_sheet(None, None, None, db, viewer, start=a.isoformat(), end=b.isoformat())
    days = [date_cls.fromisoformat(d) for d in sheet["days"]]
    ids = [p["user_id"] for p in sheet["people"]]
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(ids)).all()} if ids else {}

    fs, _ = att._day_window_utc(a)
    _, fe = att._day_window_utc(b)
    vrows = db.query(models.Visit.officer_id, models.Visit.created_at, models.Visit.paid,
                     models.Visit.amount_collected).filter(
        models.Visit.officer_id.in_(ids or [-1]), models.Visit.created_at >= fs,
        models.Visit.created_at < fe).all()
    visits: dict = defaultdict(dict)
    for uid, ts, paid, amt in vrows:
        d = _ist(ts)
        if not d:
            continue
        v = visits[uid].setdefault(d.date().isoformat(), {"n": 0, "paid": 0, "slots": [0, 0, 0, 0], "first": None, "last": None})
        v["n"] += 1
        if paid or float(amt or 0) > 0:
            v["paid"] += 1
        for i, (_l, lo, hi) in enumerate(SLOTS):
            if (i == 0 and d.hour < hi) or lo <= d.hour < hi:
                v["slots"][i] += 1
                break
        v["first"] = ts if not v["first"] or ts < v["first"] else v["first"]
        v["last"] = ts if not v["last"] or ts > v["last"] else v["last"]

    arows = {}
    for r in db.query(models.Attendance).filter(models.Attendance.user_id.in_(ids or [-1]),
                                                models.Attendance.date >= a, models.Attendance.date <= b).all():
        arows[(r.user_id, r.date.isoformat())] = r

    bl = (branch or "").strip().lower()
    people = []
    for p in sheet["people"]:
        u = users.get(p["user_id"])
        if not u or not (_is_fos(u) or visits.get(u.id)):
            continue
        if bl and (u.branch or "").strip().lower() != bl:
            continue
        people.append({"u": u, "codes": p["days"]})
    people.sort(key=lambda x: ((x["u"].branch or "zzz").upper(), (x["u"].name or "").upper()))
    return people, days, visits, arows


def _day_code(u, d, code, v, today, checked_in=False):
    """Monthly-sheet cell: visit count or Sun / A / IN-A / NA (blank for future days)."""
    jd = getattr(u, "joining_date", None)
    left = getattr(u, "blocked_at", None)
    if (jd and d < jd) or (left and not u.is_active and d > (left.date() if hasattr(left, "date") else left)):
        return "NA"
    if d > today:
        return None
    n = (v or {}).get("n", 0)
    if n:
        return n
    if code == "W":
        return "Sun"
    if code == "LV" or (code == "H•" and not checked_in):
        return "IN-A"
    if code in ("P", "L", "H", "H•") or checked_in:
        return 0
    if d.weekday() == 6:
        return "Sun"
    return "A"


STATUS = {"P": "PRESENT", "L": "PRESENT", "H": "HALF-DAY", "H•": "HALF-DAY", "LV": "LEAVE", "W": "SUNDAY", "A": "ABSENT"}


# ---------------------------------------------------------------------------------------- styles

def _styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    s = Side(style="thin", color="CBD5E1")
    return {
        "B": Border(left=s, right=s, top=s, bottom=s),
        "C": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "L": Alignment(horizontal="left", vertical="center", wrap_text=True),
        "fill": lambda c: PatternFill("solid", fgColor=c),
        "font": lambda **k: Font(**k),
    }


def _hdr(ws, r, c, text, color, S, fc="FFFFFF", size=10):
    cell = ws.cell(row=r, column=c, value=text)
    cell.fill, cell.font, cell.alignment, cell.border = S["fill"](color), S["font"](bold=True, color=fc, size=size), S["C"], S["B"]
    return cell


# ---------------------------------------------------------------------------------------- daily

def _ordinal(d: date_cls) -> str:
    n = d.day
    suf = "th" if 11 <= n <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf} {d.strftime('%B').upper()} {d.year}"


def _daily_row(db, p, d: date_cls, visits, arows, today) -> dict:
    """One FOS on one day — shared by the Excel sheet and the on-screen preview."""
    u, iso = p["u"], d.isoformat()
    code = p["codes"].get(iso, "")
    v = visits.get(u.id, {}).get(iso) or {"n": 0, "paid": 0, "slots": [0, 0, 0, 0], "first": None, "last": None}
    a = arows.get((u.id, iso))
    jd = getattr(u, "joining_date", None)
    status = "NOT JOINED" if (jd and d < jd) else ("" if d > today else STATUS.get(code, ""))
    if v["n"] and status in ("", "ABSENT", "SUNDAY", "LEAVE"):
        status = "PRESENT"
    start = a.check_in_at if a and a.check_in_at else v["first"]
    end = (a.check_out_at if a and a.check_out_at else None) or v["last"]
    remarks = []
    if code == "L":
        remarks.append("LATE START")
    if code in ("LV", "H•"):
        lv = att._leave_for(db, u.id, d)
        remarks.append(("LEAVE" + (f" – {lv.reason}" if lv and lv.reason else "")) if code == "LV" else "HALF-DAY LEAVE")
    if status in ("PRESENT", "HALF-DAY") and v["n"] == 0 and d <= today:
        remarks.append("NO VISITS")
    if code == "W":
        remarks.append("SUNDAY")
    return {"user_id": u.id, "name": u.name or "", "area": _area(u), "phone": u.phone or "",
            "branch": (u.branch or "").upper(), "first_start": _t(start), "total": v["n"], "paid": v["paid"],
            "slots": list(v["slots"]), "status": status, "remarks": " // ".join(remarks),
            "start": _t(a.check_in_at) if a and a.check_in_at else "", "end": _t(end), "code": code}


def _daily_sheet(wb, db, d: date_cls, people, visits, arows, today, S):
    from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule
    from openpyxl.utils import get_column_letter as L
    ws = wb.create_sheet(f"{d.day}-{d.month}-{d.year}")
    iso = d.isoformat()
    cols = ["S.NO", "FOS NAMES", "AREA", "CONTACT NUMBER", "REPORTING BRANCH", "FIRST START TIME", "TOTAL VISITS",
            "PRODUCTIVE VISIT (PAID)", "8-11AM", "11-1PM", "1-4PM", "4-7PM", "PRESENT", "REMARKS", "START TIME", "END TIME"]
    C0 = 2                                         # data starts in column B, like the team sheet
    last = C0 + len(cols) - 1
    ws.merge_cells(start_row=2, start_column=C0, end_row=2, end_column=last)
    t = ws.cell(row=2, column=C0, value="TODAY FIELD VISIT REPORT")
    t.fill, t.font, t.alignment = S["fill"](GREEN), S["font"](bold=True, size=16, color="FFFFFF"), S["C"]
    ws.row_dimensions[2].height = 28
    ws.merge_cells(start_row=3, start_column=C0 + 1, end_row=3, end_column=C0 + 3)
    _hdr(ws, 3, C0 + 1, _ordinal(d) + f"  ·  {d.strftime('%A')}", CYAN, S, size=12)
    ws.merge_cells(start_row=3, start_column=C0 + 8, end_row=3, end_column=C0 + 9)
    _hdr(ws, 3, C0 + 8, "MORNING", YELLOW, S, fc="7C2D12", size=11)
    ws.merge_cells(start_row=3, start_column=C0 + 10, end_row=3, end_column=C0 + 11)
    _hdr(ws, 3, C0 + 10, "EVENING", "FDBA74", S, fc="7C2D12", size=11)
    hr = 4
    for j, h in enumerate(cols):
        color = NAVY
        if h in ("8-11AM", "11-1PM"):
            color = "B45309"
        elif h in ("1-4PM", "4-7PM"):
            color = "C2410C"
        elif h in ("TOTAL VISITS", "PRODUCTIVE VISIT (PAID)"):
            color = GREEN
        elif h == "PRESENT":
            color = CYAN
        _hdr(ws, hr, C0 + j, h, color, S)
    ws.row_dimensions[hr].height = 32

    r = hr
    for i, p in enumerate(people, 1):
        d_row = _daily_row(db, p, d, visits, arows, today)
        r += 1
        row = [i, d_row["name"], d_row["area"], d_row["phone"], d_row["branch"], d_row["first_start"], None,
               d_row["paid"] or None] + [x or None for x in d_row["slots"]] + \
              [d_row["status"], d_row["remarks"] or None, d_row["start"], d_row["end"]]
        for j, val in enumerate(row):
            c = ws.cell(row=r, column=C0 + j, value=val)
            c.border, c.alignment = S["B"], (S["L"] if j in (1, 2, 4, 13) else S["C"])
        ws.cell(row=r, column=C0 + 6, value=f"=SUM({L(C0 + 8)}{r}:{L(C0 + 11)}{r})")
        ws.cell(row=r, column=C0 + 6).font = S["font"](bold=True)
        ws.cell(row=r, column=C0 + 1).font = S["font"](bold=True)
        if i % 2 == 0:
            for j in range(len(cols)):
                if j not in (6, 12):
                    ws.cell(row=r, column=C0 + j).fill = S["fill"]("F8FAFC")
    first, lastr = hr + 1, r
    if people:
        r += 1
        ws.cell(row=r, column=C0 + 1, value=f"TOTAL  ({len(people)} FOS)")
        for j in (6, 7, 8, 9, 10, 11):
            col = L(C0 + j)
            ws.cell(row=r, column=C0 + j, value=f"=SUBTOTAL(9,{col}{first}:{col}{lastr})")
        ws.cell(row=r, column=C0 + 12, value=f'=COUNTIF({L(C0 + 12)}{first}:{L(C0 + 12)}{lastr},"PRESENT")&" present"')
        for j in range(len(cols)):
            c = ws.cell(row=r, column=C0 + j)
            c.fill, c.font, c.border, c.alignment = S["fill"]("DCE6FA"), S["font"](bold=True), S["B"], S["C"]
        # conditional formats: status colours, zero-visit present rows, visit heat
        rng = f"{L(C0 + 12)}{first}:{L(C0 + 12)}{lastr}"
        for txt, bg, fg in (("PRESENT", "C6EFCE", "166534"), ("HALF-DAY", "FED7AA", "9A3412"), ("ABSENT", "FFC7CE", "B91C1C"),
                            ("LEAVE", "BDD7EE", "1E40AF"), ("SUNDAY", "E2E8F0", "475569"), ("NOT JOINED", "E5E7EB", "6B7280")):
            ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{txt}"'],
                                                          fill=S["fill"](bg), font=S["font"](bold=True, color=fg)))
        tv = f"{L(C0 + 6)}{first}:{L(C0 + 6)}{lastr}"
        ws.conditional_formatting.add(tv, ColorScaleRule(start_type="num", start_value=0, start_color="FCA5A5",
                                                         mid_type="num", mid_value=5, mid_color="FDE68A",
                                                         end_type="num", end_value=12, end_color="86EFAC"))
        pv = f"{L(C0 + 7)}{first}:{L(C0 + 7)}{lastr}"
        ws.conditional_formatting.add(pv, CellIsRule(operator="greaterThan", formula=["0"],
                                                     fill=S["fill"]("BBF7D0"), font=S["font"](bold=True, color="166534")))
        ws.conditional_formatting.add(f"{L(C0 + 5)}{first}:{L(C0 + 5)}{lastr}",
                                      FormulaRule(formula=[f'{L(C0 + 13)}{first}="LATE START"'], fill=S["fill"]("FEF3C7")))
        ws.auto_filter.ref = f"{L(C0)}{hr}:{L(last)}{lastr}"
        _branch_summary(ws, r + 3, C0, people, visits, iso, S)
    widths = [6, 30, 22, 15, 18, 12, 10, 13, 9, 9, 9, 9, 13, 30, 11, 11]
    ws.column_dimensions["A"].width = 2
    for j, w in enumerate(widths):
        ws.column_dimensions[L(C0 + j)].width = w
    ws.freeze_panes = ws.cell(row=hr + 1, column=C0 + 2)
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_title_rows = f"{hr}:{hr}"
    return ws


def _branch_summary(ws, r, C0, people, visits, iso, S):
    hdr = ["BRANCH", "FOS", "PRESENT", "TOTAL VISITS", "PAID VISITS", "AVG VISITS / PRESENT FOS", "ZERO-VISIT FOS"]
    ws.merge_cells(start_row=r, start_column=C0 + 1, end_row=r, end_column=C0 + len(hdr))
    _hdr(ws, r, C0 + 1, "BRANCH SUMMARY", NAVY, S, size=11)
    for j, h in enumerate(hdr):
        _hdr(ws, r + 1, C0 + 1 + j, h, BLUE, S)
    agg: dict = {}
    for p in people:
        u, code = p["u"], p["codes"].get(iso, "")
        v = visits.get(u.id, {}).get(iso) or {"n": 0, "paid": 0}
        b = (u.branch or "—").upper()
        g = agg.setdefault(b, [0, 0, 0, 0, 0])
        g[0] += 1
        pres = code in ("P", "L", "H", "H•") or v["n"] > 0
        g[1] += 1 if pres else 0
        g[2] += v["n"]; g[3] += v["paid"]
        g[4] += 1 if (pres and v["n"] == 0) else 0
    rr = r + 1
    for b, g in sorted(agg.items()):
        rr += 1
        vals = [b, g[0], g[1], g[2], g[3], round(g[2] / g[1], 1) if g[1] else 0, g[4]]
        for j, val in enumerate(vals):
            c = ws.cell(row=rr, column=C0 + 1 + j, value=val)
            c.border, c.alignment = S["B"], S["L"] if j == 0 else S["C"]
            if j == 0:
                c.font = S["font"](bold=True)




@router.get("/daily.xlsx")
def daily_report(start: str | None = None, end: str | None = None, branch: str | None = None,
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    import openpyxl
    from openpyxl.utils import get_column_letter as L
    a, b = _parse_range(start, end, default_cycle=False)
    if (b - a).days > 31:
        raise HTTPException(status_code=400, detail="The daily report covers at most 31 days.")
    people, days, visits, arows = _collect(db, user, a, b, branch)
    today = att._ist_today()
    S = _styles()
    wb = openpyxl.Workbook()
    summ = wb.active
    summ.title = "Summary"
    for d in days:
        _daily_sheet(wb, db, d, people, visits, arows, today, S)

    # Summary: one row per FOS across the range
    n = len(days)
    label = _ordinal(a) if a == b else f"{_ordinal(a)}  →  {_ordinal(b)}"
    cols = ["S.NO", "FOS NAMES", "AREA", "CONTACT NUMBER", "BRANCH", "DAYS PRESENT", "TOTAL VISITS", "PAID VISITS",
            "AVG VISITS / DAY", "8-11AM", "11-1PM", "1-4PM", "4-7PM", "ZERO-VISIT DAYS", "LATE STARTS", "ABSENT DAYS"]
    summ.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(cols))
    t = summ.cell(row=1, column=1, value=f"FOS FIELD VISIT SUMMARY — {label}")
    t.fill, t.font, t.alignment = S["fill"](GREEN), S["font"](bold=True, size=15, color="FFFFFF"), S["C"]
    summ.row_dimensions[1].height = 26
    summ.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(cols))
    summ.cell(row=2, column=1, value=f"{len(people)} field agents · {n} day(s){' · Branch: ' + branch if branch else ''}"
              f" · Generated {att._ist_now():%d-%b-%Y %I:%M %p} by {user.name or ''} · one sheet per day follows").font = \
        S["font"](size=10, color="475569")
    for j, h in enumerate(cols, 1):
        _hdr(summ, 3, j, h, GREEN if "VISIT" in h else NAVY, S)
    summ.row_dimensions[3].height = 30
    for i, p in enumerate(people, 1):
        u = p["u"]
        tot = paid = pres = zero = late = absent = 0
        sl = [0, 0, 0, 0]
        for d in days:
            iso = d.isoformat()
            code = p["codes"].get(iso, "")
            v = visits.get(u.id, {}).get(iso) or {"n": 0, "paid": 0, "slots": [0, 0, 0, 0]}
            tot += v["n"]; paid += v["paid"]
            sl = [x + y for x, y in zip(sl, v["slots"])]
            is_p = code in ("P", "L", "H", "H•") or v["n"] > 0
            pres += 1 if is_p else 0
            zero += 1 if (is_p and v["n"] == 0) else 0
            late += 1 if code == "L" else 0
            absent += 1 if code == "A" and d <= today else 0
        r = 3 + i
        vals = [i, u.name, _area(u), u.phone or "", (u.branch or "").upper(), pres, tot, paid,
                f"=IFERROR(ROUND({L(7)}{r}/{L(6)}{r},1),0)"] + sl + [zero, late, absent]
        for j, val in enumerate(vals, 1):
            c = summ.cell(row=r, column=j, value=val)
            c.border, c.alignment = S["B"], S["L"] if j in (2, 3, 5) else S["C"]
        summ.cell(row=r, column=2).font = S["font"](bold=True)
    if people:
        from openpyxl.formatting.rule import ColorScaleRule
        lr = 3 + len(people)
        summ.conditional_formatting.add(f"I4:I{lr}", ColorScaleRule(start_type="min", start_color="FCA5A5", mid_type="percentile",
                                                                    mid_value=50, mid_color="FDE68A", end_type="max", end_color="86EFAC"))
        summ.conditional_formatting.add(f"G4:G{lr}", ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color="86EFAC"))
        summ.auto_filter.ref = f"A3:{L(len(cols))}{lr}"
    for j, w in enumerate([6, 30, 22, 15, 16, 10, 10, 10, 11, 9, 9, 9, 9, 11, 10, 10], 1):
        summ.column_dimensions[L(j)].width = w
    summ.freeze_panes = "C4"
    summ.page_setup.orientation = "landscape"
    summ.sheet_properties.pageSetUpPr.fitToPage = True
    summ.page_setup.fitToWidth, summ.page_setup.fitToHeight = 1, 0

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    audit.record(db, user, "download", None, entity_type="download",
                 detail=f"Downloaded FOS daily visit report {a}..{b}")
    db.commit()
    fn = f"FOS_Daily_Visit_Report_{a:%d-%m-%Y}" + ("" if a == b else f"_to_{b:%d-%m-%Y}") + ".xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


# ---------------------------------------------------------------------------------------- monthly

@router.get("/monthly.xlsx")
def monthly_report(start: str | None = None, end: str | None = None, branch: str | None = None,
                   db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    import openpyxl
    from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
    from openpyxl.utils import get_column_letter as L
    a, b = _parse_range(start, end, default_cycle=True)
    people, days, visits, arows = _collect(db, user, a, b, branch)
    today = att._ist_today()
    S = _styles()
    n = len(days)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{a:%b}-{b:%b}".upper()

    C0 = 3                                              # S.NO in column C, like the team sheet
    D0 = C0 + 5                                         # first day column (H)
    DL = D0 + n - 1                                     # last day column
    stats = ["TOTAL COUNT", "AVG VISIT COUNT", "WORKING DAYS", "JOININGS (NA)", "ZERO COUNT", "1'S COUNT",
             "2'S COUNT", "3'S COUNT", "ABOVE 4'S COUNT", "SUNDAY", "ABSENTS", "LEAVE (IN-A)", "REASONS"]
    S0 = DL + 1
    P0 = S0 + len(stats)                                # productive (paid) block
    PL = P0 + n - 1
    TP = PL + 1
    lastcol = TP

    # ---- title block
    ws.cell(row=2, column=C0, value="Month").font = S["font"](bold=True, color="475569")
    ws.cell(row=2, column=C0 + 1, value=f"{a:%B} {a.day}{'ST' if a.day == 21 else ''} TO {b:%B} {b.day}TH".upper()).font = S["font"](bold=True, size=12, color=NAVY)
    ws.cell(row=3, column=C0, value="Year").font = S["font"](bold=True, color="475569")
    ws.cell(row=3, column=C0 + 1, value=b.year).font = S["font"](bold=True, size=12, color=NAVY)
    ws.merge_cells(start_row=2, start_column=D0, end_row=3, end_column=DL)
    t = ws.cell(row=2, column=D0, value="FOS ATTENDANCE & VISIT SHEET")
    t.fill, t.font, t.alignment = S["fill"](NAVY), S["font"](bold=True, size=18, color="FFFFFF"), S["C"]
    ws.cell(row=4, column=D0, value=f"{len(people)} field agents{' · Branch: ' + branch if branch else ''} · numbers = visits that day · "
            f"generated {att._ist_now():%d-%b-%Y %I:%M %p} by {user.name or ''} from RecoverIQ").font = S["font"](size=9, color="64748B")

    # ---- row 6: day totals (filter-aware), row 7: band titles, rows 8-9: headers
    first, lastr = 10, 9 + len(people)
    for k in range(n):
        for col in (D0 + k, P0 + k):
            c = ws.cell(row=6, column=col, value=f"=SUBTOTAL(9,{L(col)}{first}:{L(col)}{max(lastr, first)})")
            c.font, c.alignment, c.fill = S["font"](bold=True, color=NAVY), S["C"], S["fill"]("E0E7FF")
    ws.cell(row=6, column=D0 - 1, value="Day total ▶").font = S["font"](bold=True, size=9, color="475569")
    ws.merge_cells(start_row=7, start_column=C0, end_row=7, end_column=S0 + len(stats) - 1)
    _hdr(ws, 7, C0, f"{_ordinal(a)}  –  {_ordinal(b)}   ·   VISIT COUNTS", GREEN, S, size=12)
    ws.merge_cells(start_row=7, start_column=P0, end_row=7, end_column=TP)
    _hdr(ws, 7, P0, "PRODUCTIVE COUNTS (PAID)", "D97706", S, size=12)
    for j, h in enumerate(["S.NO", "FOS NAMES", "AREA", "CONTACT NUMBER", "BRANCH"]):
        ws.merge_cells(start_row=8, start_column=C0 + j, end_row=9, end_column=C0 + j)
        _hdr(ws, 8, C0 + j, h, NAVY, S)
        ws.cell(row=9, column=C0 + j).border = S["B"]
    for k, d in enumerate(days):
        sun = d.weekday() == 6
        _hdr(ws, 8, D0 + k, d.day, "64748B" if sun else BLUE, S)
        _hdr(ws, 9, D0 + k, d.strftime("%a"), "94A3B8" if sun else "3B82F6", S, size=9)
        ws.merge_cells(start_row=8, start_column=P0 + k, end_row=9, end_column=P0 + k)
        _hdr(ws, 8, P0 + k, f"{d.strftime('%b').upper()} {d.day}", "94A3B8" if sun else "F59E0B", S, size=9)
    for j, h in enumerate(stats):
        ws.merge_cells(start_row=8, start_column=S0 + j, end_row=9, end_column=S0 + j)
        _hdr(ws, 8, S0 + j, h, "0F766E" if j < 3 else "7C3AED" if j < 9 else "B91C1C" if j < 12 else NAVY, S, size=9)
    ws.merge_cells(start_row=8, start_column=TP, end_row=9, end_column=TP)
    _hdr(ws, 8, TP, "TOTAL PAID COUNT", "B45309", S, size=9)
    ws.row_dimensions[8].height = 30

    # ---- one row per FOS
    for i, p in enumerate(people):
        u = p["u"]
        r = first + i
        base = [i + 1, u.name or "", _area(u), u.phone or "", (u.branch or "").upper()]
        for j, val in enumerate(base):
            c = ws.cell(row=r, column=C0 + j, value=val)
            c.border, c.alignment = S["B"], S["L"] if j in (1, 2, 4) else S["C"]
        ws.cell(row=r, column=C0 + 1).font = S["font"](bold=True)
        reasons = []
        for k, d in enumerate(days):
            iso = d.isoformat()
            v = visits.get(u.id, {}).get(iso)
            code = p["codes"].get(iso, "")
            ar = arows.get((u.id, iso))
            val = _day_code(u, d, code, v, today, bool(ar and ar.check_in_at))
            c = ws.cell(row=r, column=D0 + k, value=val)
            c.border, c.alignment = S["B"], S["C"]
            pv = None if val in (None, "NA") else (v or {}).get("paid", 0)
            c2 = ws.cell(row=r, column=P0 + k, value=pv)
            c2.border, c2.alignment = S["B"], S["C"]
            if code == "LV":
                lv = att._leave_for(db, u.id, d)
                if lv and lv.reason:
                    reasons.append(f"{d.day}/{d.month}: {lv.reason}")
        rng = f"{L(D0)}{r}:{L(DL)}{r}"
        f = {
            "TOTAL COUNT": f"=SUM({rng})",
            "AVG VISIT COUNT": f"=IFERROR(ROUND({L(S0)}{r}/{L(S0 + 2)}{r},1),0)",
            "WORKING DAYS": f'=COUNTIF({rng},">0")+{L(S0 + 4)}{r}',
            "JOININGS (NA)": f'=COUNTIF({rng},"NA")',
            "ZERO COUNT": f"=COUNTIF({rng},0)",
            "1'S COUNT": f"=COUNTIF({rng},1)",
            "2'S COUNT": f"=COUNTIF({rng},2)",
            "3'S COUNT": f"=COUNTIF({rng},3)",
            "ABOVE 4'S COUNT": f'=COUNTIF({rng},">=4")',
            "SUNDAY": f'=COUNTIF({rng},"Sun")',
            "ABSENTS": f'=COUNTIF({rng},"A")',
            "LEAVE (IN-A)": f'=COUNTIF({rng},"IN-A")',
            "REASONS": "; ".join(reasons) or None,
        }
        for j, h in enumerate(stats):
            c = ws.cell(row=r, column=S0 + j, value=f[h])
            c.border, c.alignment = S["B"], S["L"] if h == "REASONS" else S["C"]
            c.font = S["font"](bold=True, color="0F766E" if j < 3 else "1F2937")
        c = ws.cell(row=r, column=TP, value=f"=SUM({L(P0)}{r}:{L(PL)}{r})")
        c.border, c.alignment, c.font = S["B"], S["C"], S["font"](bold=True, color="B45309")
        if i % 2 == 1:
            for j in range(5):
                ws.cell(row=r, column=C0 + j).fill = S["fill"]("F8FAFC")

    if people:
        days_rng = f"{L(D0)}{first}:{L(DL)}{lastr}"
        for txt, bg, fg in (('"Sun"', "F2DCDB", "9B2C2C"), ('"A"', "FDE047", "DC2626"), ('"NA"', "E5E7EB", "6B7280"),
                            ('"IN-A"', "BFDBFE", "1E40AF")):
            ws.conditional_formatting.add(days_rng, CellIsRule(operator="equal", formula=[txt], fill=S["fill"](bg),
                                                               font=S["font"](bold=True, color=fg)))
        ws.conditional_formatting.add(days_rng, CellIsRule(operator="equal", formula=["0"], fill=S["fill"]("FECACA"),
                                                           font=S["font"](bold=True, color="B91C1C")))
        ws.conditional_formatting.add(days_rng, CellIsRule(operator="between", formula=["1", "3"], fill=S["fill"]("FEF3C7")))
        ws.conditional_formatting.add(days_rng, CellIsRule(operator="greaterThanOrEqual", formula=["4"], fill=S["fill"]("BBF7D0"),
                                                           font=S["font"](bold=True, color="166534")))
        paid_rng = f"{L(P0)}{first}:{L(PL)}{lastr}"
        ws.conditional_formatting.add(paid_rng, CellIsRule(operator="greaterThan", formula=["0"], fill=S["fill"]("FDE68A"),
                                                           font=S["font"](bold=True, color="92400E")))
        for col in (S0, S0 + 1, TP):
            ws.conditional_formatting.add(f"{L(col)}{first}:{L(col)}{lastr}",
                                          ColorScaleRule(start_type="min", start_color="FCA5A5", mid_type="percentile",
                                                         mid_value=50, mid_color="FEF08A", end_type="max", end_color="86EFAC"))
        ws.auto_filter.ref = f"{L(C0)}9:{L(lastcol)}{lastr}"

    ws.column_dimensions["A"].width = 2; ws.column_dimensions["B"].width = 2
    for j, w in enumerate([6, 30, 22, 14, 16]):
        ws.column_dimensions[L(C0 + j)].width = w
    for k in range(n):
        ws.column_dimensions[L(D0 + k)].width = 5.2
        ws.column_dimensions[L(P0 + k)].width = 7
    for j in range(len(stats)):
        ws.column_dimensions[L(S0 + j)].width = 40 if stats[j] == "REASONS" else 9.5
    ws.column_dimensions[L(TP)].width = 10
    ws.freeze_panes = ws.cell(row=first, column=D0)
    ws.sheet_view.zoomScale = 85
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_title_rows = "8:9"

    # ---- legend
    lg = wb.create_sheet("Legend")
    lg.append(["Code / column", "Meaning"])
    for c in lg[1]:
        c.fill, c.font, c.border = S["fill"](NAVY), S["font"](bold=True, color="FFFFFF"), S["B"]
    for code, bg, meaning in [
        ("number", "BBF7D0", "Visits logged that day in RecoverIQ (green = 4 or more, amber = 1–3)"),
        ("0", "FECACA", "Checked in / present but no visit logged"),
        ("Sun", "F2DCDB", "Sunday (no visits). A Sunday with visits shows the count"),
        ("A", "FDE047", "Absent — no check-in, no visit, no approved leave"),
        ("IN-A", "BFDBFE", "Informed absence — approved leave"),
        ("NA", "E5E7EB", "Not applicable — before joining date / after leaving"),
        ("(blank)", "FFFFFF", "Future date"),
        ("TOTAL COUNT", "FFFFFF", "Sum of visits in the cycle"),
        ("WORKING DAYS", "FFFFFF", "Days with at least one visit + present days with zero visits"),
        ("AVG VISIT COUNT", "FFFFFF", "TOTAL COUNT ÷ WORKING DAYS"),
        ("PRODUCTIVE (PAID)", "FDE68A", "Visits where payment was collected (marked paid / amount > 0)"),
        ("Day total row", "E0E7FF", "Row 6 totals each day — follows the filter (SUBTOTAL)"),
    ]:
        lg.append([code, meaning])
        rr = lg.max_row
        lg.cell(row=rr, column=1).fill = S["fill"](bg)
        for j in (1, 2):
            lg.cell(row=rr, column=j).border = S["B"]
            lg.cell(row=rr, column=j).alignment = S["C"] if j == 1 else S["L"]
        lg.cell(row=rr, column=1).font = S["font"](bold=True)
    lg.column_dimensions["A"].width = 20
    lg.column_dimensions["B"].width = 90

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    audit.record(db, user, "download", None, entity_type="download",
                 detail=f"Downloaded FOS monthly visit sheet {a}..{b}")
    db.commit()
    fn = f"FOS_Visit_Attendance_{a:%d%b}-{b:%d%b%Y}.xlsx".upper().replace(".XLSX", ".xlsx")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


# ---------------------------------------------------------------------------------------- previews
# Same numbers as the Excel files, as JSON for the on-screen preview in Attendance → FOS visit reports.

@router.get("/daily")
def daily_preview(start: str | None = None, end: str | None = None, branch: str | None = None,
                  db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    a, b = _parse_range(start, end, default_cycle=False)
    if (b - a).days > 31:
        raise HTTPException(status_code=400, detail="The daily report covers at most 31 days.")
    people, days, visits, arows = _collect(db, user, a, b, branch)
    today = att._ist_today()
    out_days = []
    for d in days:
        rows = [_daily_row(db, p, d, visits, arows, today) for p in people]
        tot = {"fos": len(rows), "present": sum(1 for r in rows if r["status"] in ("PRESENT", "HALF-DAY")),
               "visits": sum(r["total"] for r in rows), "paid": sum(r["paid"] for r in rows),
               "slots": [sum(r["slots"][k] for r in rows) for k in range(4)],
               "zero": sum(1 for r in rows if r["status"] in ("PRESENT", "HALF-DAY") and r["total"] == 0)}
        out_days.append({"date": d.isoformat(), "label": _ordinal(d) + " · " + d.strftime("%A"), "rows": rows, "totals": tot})
    return {"start": a.isoformat(), "end": b.isoformat(), "slots": [s_[0] for s_ in SLOTS], "days": out_days}


@router.get("/monthly")
def monthly_preview(start: str | None = None, end: str | None = None, branch: str | None = None,
                    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    a, b = _parse_range(start, end, default_cycle=True)
    people, days, visits, arows = _collect(db, user, a, b, branch)
    today = att._ist_today()
    rows = []
    for p in people:
        u = p["u"]
        cells, paid = [], []
        for d in days:
            iso = d.isoformat()
            v = visits.get(u.id, {}).get(iso)
            ar = arows.get((u.id, iso))
            val = _day_code(u, d, p["codes"].get(iso, ""), v, today, bool(ar and ar.check_in_at))
            cells.append(val)
            paid.append(None if val in (None, "NA") else (v or {}).get("paid", 0))
        nums = [c for c in cells if isinstance(c, int)]
        total = sum(nums)
        working = sum(1 for c in nums if c > 0) + sum(1 for c in nums if c == 0)
        cnt = lambda x: sum(1 for c in cells if c == x)
        rows.append({
            "user_id": u.id, "name": u.name or "", "area": _area(u), "phone": u.phone or "", "branch": (u.branch or "").upper(),
            "days": cells, "paid": paid, "total": total, "working_days": working,
            "avg": round(total / working, 1) if working else 0,
            "na": cnt("NA"), "zero": cnt(0), "ones": cnt(1), "twos": cnt(2), "threes": cnt(3),
            "four_plus": sum(1 for c in nums if c >= 4), "sundays": cnt("Sun"), "absents": cnt("A"),
            "leave": cnt("IN-A"), "total_paid": sum(x or 0 for x in paid),
        })
    day_tot = [sum(r["days"][k] for r in rows if isinstance(r["days"][k], int)) for k in range(len(days))]
    return {"start": a.isoformat(), "end": b.isoformat(),
            "label": f"{_ordinal(a)} – {_ordinal(b)}",
            "days": [{"date": d.isoformat(), "day": d.day, "dow": d.strftime("%a"), "sun": d.weekday() == 6} for d in days],
            "day_totals": day_tot, "rows": rows}
