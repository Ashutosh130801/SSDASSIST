"""MIS PIVOT workbook — the team's own pivot MIS (ICICI X-BKT format), filled from live RecoverIQ data.

The template (app/assets/mis_pivot_template.xlsx, built once by build_mis_pivot_template.py from the
team's workbook) carries the 10 real pivot tables, the 6 slicers (CYC, CALLER, AREA, FOS NAME, DATE,
V DATE), page filters and the RecoverIQ look. For each download we:
  1. write the MAIN sheet (same 46 columns as the team's MAIN sheet) from RecoverIQ cases,
  2. rebuild the pivot cache (shared items + records), pivot field items and slicer items so the
     pivots/slicers match the new data (pivots refresh on open),
  3. regenerate the two FOS TARGET tables: ALL (follows the slicers, via GETPIVOTDATA) and
     SELECTED CYCLE (pick a cycle in the yellow cell).
Nothing here writes to the database.
"""
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ASSET = Path(__file__).parent / "assets" / "mis_pivot_template.xlsx"
META = Path(__file__).parent / "assets" / "mis_pivot_template.json"
IST = timezone(timedelta(hours=5, minutes=30))

COLUMNS = ["ACC.NO", "NAMES", "O/N", "CYC", "MOBILE", "BLOCK", "EXCESS LIMIT", "CREDIT", "ENR", "EMI 0/S",
           "CURR_BAL", "PRI", "NORM", "STAB", "PAID/UNPAID", "STATUS", "AMOUNT", "PENDING", "DATE", "DONE BY",
           "MODE", "TL ID", "CALLER", "CALLER ID", "CAT ALLO", "ADD 1", "ADD 2", "LOCATION", "AREA", "FOS NAME",
           "FOS ID", "MARC", "MARC ID", "MARC PW", "IQ UPLOAD", "TC REMARK", "VISITS", "FOS DISPO", "REMARKS",
           "V DATE", "LAST PAYMENT DATE", "LAST PAYMENT AMOUNT", "UCIC DODE", "CARD TYPE", "ALLOC DATE", "DueDate"]
CI = {c: i for i, c in enumerate(COLUMNS)}
# fields the pivots / slicers group by → need shared items in the pivot cache
ITEM_FIELDS = {"CYC", "PAID/UNPAID", "STATUS", "DATE", "CALLER", "CAT ALLO", "AREA", "FOS NAME", "VISITS", "V DATE"}
MONEY = {"EXCESS LIMIT", "CREDIT", "ENR", "EMI 0/S", "CURR_BAL", "PRI", "NORM", "STAB", "AMOUNT", "PENDING",
         "LAST PAYMENT AMOUNT"}
ALWAYS_NUM = {"ENR", "AMOUNT", "NORM", "STAB", "PENDING", "CURR_BAL", "PRI"}   # never blank (SUMPRODUCT safe)
DEFAULT_TARGET = 0.85


# ───────────────────────────────────────── rows from RecoverIQ ─────────────────────────────────────────
def person_label(u, code=None):
    """RAVI KUMAR (FO047) / AREA / 9876543210 — area / phone only when known."""
    if not u:
        return ""
    code = code or u.emp_code or ""
    s = f"{(u.name or '').strip()}" + (f" ({code})" if code else "")
    area = (getattr(u, "location", None) or "").strip()
    if area:
        s += f" / {area}"
    if (u.phone or "").strip():
        s += f" / {u.phone.strip()}"
    return s


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _d(dt):
    if not dt:
        return ""
    if isinstance(dt, datetime):
        dt = (dt.astimezone(IST) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(IST)).date()
    try:
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return str(dt)


def build_rows(db, cases):
    """MAIN-sheet rows (46 columns) + {FOS label: target fraction} for these cases."""
    from . import models
    ids = [c.id for c in cases]
    uids = {i for c in cases for i in (c.assigned_fos_id, c.assigned_caller_id, c.esc_prev_fos_id, c.esc_prev_caller_id) if i}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(uids or [-1])).all()}
    # latest visit + whether any visit, per case
    last_visit, visited = {}, set()
    last_pay = {}                 # case_id -> (datetime, 'TC'|'FE', amount) — the latest collection

    def _aware(dt):
        if not dt:
            return datetime.min.replace(tzinfo=timezone.utc)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def _note_pay(cid, when, who, amt):
        cur = last_pay.get(cid)
        if not cur or _aware(when) >= _aware(cur[0]):
            last_pay[cid] = (when, who, amt)

    for k in range(0, len(ids), 900):
        chunk = ids[k:k + 900]
        for v in (db.query(models.Visit).filter(models.Visit.case_id.in_(chunk)).all()):
            visited.add(v.case_id)
            if v.case_id not in last_visit or _aware(v.created_at) >= _aware(last_visit[v.case_id].created_at):
                last_visit[v.case_id] = v
            if _num(v.amount_collected):
                _note_pay(v.case_id, v.created_at, "FE", _num(v.amount_collected))
        for cl in (db.query(models.CallLog).filter(models.CallLog.case_id.in_(chunk),
                                                   models.CallLog.disposition.in_(["PAYMENT", "PAID"])).all()):
            if _num(cl.ptp_amount):
                _note_pay(cl.case_id, cl.created_at, "TC", _num(cl.ptp_amount))

    def code_for(u, role):
        if not u:
            return ""
        if role == "fos" and u.role != "fos" and getattr(u, "fos_emp_code", None):
            return u.fos_emp_code
        if role == "caller" and u.role != "telecaller" and getattr(u, "tc_emp_code", None):
            return u.tc_emp_code
        return u.emp_code or ""

    rows = []
    for c in cases:
        _x = c.extra or {}
        x = {**{k[2:]: v for k, v in _x.items() if k.startswith("x_")}, **{k: v for k, v in _x.items() if not k.startswith("x_")}}
        fu = users.get(c.assigned_fos_id or c.esc_prev_fos_id)
        cu = users.get(c.assigned_caller_id or c.esc_prev_caller_id)
        paid = (c.paid_status or "").upper() == "PAID"
        ns = (c.norm_stab or "").upper()
        status = (ns if ns in ("NORM", "STAB") else "STAB") if paid else "RF"
        cyc = c.cycle
        cyc = int(cyc) if str(cyc or "").strip().isdigit() else (str(cyc).strip() if cyc else "")
        lv = last_visit.get(c.id)
        lp = last_pay.get(c.id)
        r = [""] * len(COLUMNS)
        r[CI["ACC.NO"]] = c.account_no or ""
        r[CI["NAMES"]] = c.customer_name or ""
        r[CI["O/N"]] = c.old_new or ""
        r[CI["CYC"]] = cyc
        r[CI["MOBILE"]] = c.phone or ""
        r[CI["BLOCK"]] = x.get("block") or c.bucket or ""
        r[CI["EXCESS LIMIT"]] = _num(x.get("excess_limit"))
        r[CI["CREDIT"]] = _num(x.get("credit"))
        r[CI["ENR"]] = _num(c.enr) or 0.0
        r[CI["EMI 0/S"]] = _num(x.get("emi_os"))
        r[CI["CURR_BAL"]] = _num(c.total_outstanding) or 0.0
        r[CI["PRI"]] = _num(c.principal_outstanding) or 0.0
        r[CI["NORM"]] = _num(c.norm_amount) or 0.0
        r[CI["STAB"]] = _num(c.stab_amount) or 0.0
        r[CI["PAID/UNPAID"]] = "PAID" if paid else "UNPAID"
        r[CI["STATUS"]] = status
        r[CI["AMOUNT"]] = _num(c.received_amount) or 0.0
        r[CI["PENDING"]] = _num(c.pending_amount) or 0.0
        r[CI["DATE"]] = _d(lp[0]) if lp else ""
        r[CI["DONE BY"]] = lp[1] if lp else ""
        r[CI["MODE"]] = x.get("mode_of_payment") or ""
        r[CI["TL ID"]] = c.team_lead or ""
        r[CI["CALLER"]] = person_label(cu, code_for(cu, "caller")) if cu else ""
        r[CI["CALLER ID"]] = code_for(cu, "caller")
        r[CI["CAT ALLO"]] = c.cat or ""
        r[CI["ADD 1"]] = c.address or ""
        r[CI["ADD 2"]] = c.address2 or ""
        r[CI["LOCATION"]] = x.get("city") or c.branch or ""
        r[CI["AREA"]] = c.team or ""
        r[CI["FOS NAME"]] = person_label(fu, code_for(fu, "fos")) if fu else "NO FOS"
        r[CI["FOS ID"]] = code_for(fu, "fos")
        for k_ in ("MARC", "MARC ID", "MARC PW", "IQ UPLOAD"):      # only if the upload sheet had them
            r[CI[k_]] = x.get(k_.lower().replace(" ", "_")) or ""
        r[CI["TC REMARK"]] = x.get("tc_remark") or ""
        r[CI["VISITS"]] = "VISITED" if c.id in visited else "NOT VISITED"
        r[CI["FOS DISPO"]] = (lv.disposition or "") if lv else ""
        r[CI["REMARKS"]] = c.remarks or ""
        r[CI["V DATE"]] = _d(lv.created_at) if lv else ""
        r[CI["LAST PAYMENT DATE"]] = str(x.get("last_payment_date") or "")[:10]
        r[CI["LAST PAYMENT AMOUNT"]] = _num(x.get("last_payment_amount"))
        r[CI["UCIC DODE"]] = x.get("ucic") or ""
        r[CI["CARD TYPE"]] = x.get("card_type") or ""
        r[CI["ALLOC DATE"]] = str(x.get("alloc_date") or "")
        r[CI["DueDate"]] = str(x.get("due_date") or "")[:10] or _d(c.close_date)
        rows.append(r)
    rows.sort(key=lambda r: (str(r[CI["FOS NAME"]]).upper(), str(r[CI["NAMES"]]).upper()))
    return rows


def targets_for(db, bank, product, rows):
    """{FOS label: fraction}. 85% unless set — a per-FOS target (emp code or name) wins over a
    portfolio-wide one ('*ALL*'), which wins over the 85% default."""
    from . import models
    t = {(m.emp_name or "").strip().upper(): float(m.target_pct or 0) / 100.0
         for m in db.query(models.MisTarget).filter(models.MisTarget.bank == bank, models.MisTarget.product == product).all()
         if m.target_pct is not None}
    base = t.get("*ALL*") or DEFAULT_TARGET
    out = {}
    for r in rows:
        lab, code = r[CI["FOS NAME"]], (r[CI["FOS ID"]] or "").upper()
        nm = lab.split(" (")[0].strip().upper()
        out[lab] = t.get(code) or t.get(lab.upper()) or t.get(nm) or base
    return out


# ───────────────────────────────────────── xlsx writer ─────────────────────────────────────────
def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _colnum(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def _cell(ref, v, s):
    if v is None or v == "":
        return f'<c r="{ref}" s="{s}"/>'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f'<c r="{ref}" s="{s}"><v>{repr(float(v)) if isinstance(v, float) else v}</v></c>'
    return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def _fcell(ref, formula, s):
    return f'<c r="{ref}" s="{s}"><f>{escape(formula)}</f></c>'


def _shared_items(vals):
    """sharedItems XML + index map for an ITEM field."""
    uniq, seen = [], set()
    for v in vals:
        k = ("n", v) if isinstance(v, (int, float)) and v != "" else ("s", str(v))
        if v in ("", None):
            k = ("m", "")
        if k not in seen:
            seen.add(k); uniq.append(k)
    nums = [v for t, v in uniq if t == "n"]
    strs = [v for t, v in uniq if t == "s"]
    blank = any(t == "m" for t, _ in uniq)
    uniq.sort(key=lambda k: (k[0] == "m", k[0] == "s", k[1] if k[0] == "n" else 0, str(k[1]).upper()))
    attrs = []
    if nums and not strs:
        attrs += ['containsSemiMixedTypes="0"' if not blank else "", 'containsString="0"', 'containsNumber="1"']
        if all(float(n).is_integer() for n in nums):
            attrs.append('containsInteger="1"')
        attrs += [f'minValue="{min(nums)}"', f'maxValue="{max(nums)}"']
    elif nums and strs:
        attrs += ['containsMixedTypes="1"', 'containsNumber="1"', f'minValue="{min(nums)}"', f'maxValue="{max(nums)}"']
    if blank:
        attrs.append('containsBlank="1"')
    body = "".join("<m/>" if t == "m" else f'<n v="{v}"/>' if t == "n" else f'<s v="{escape(str(v), {chr(34): "&quot;"})}"/>'
                   for t, v in uniq)
    idx = {k: i for i, k in enumerate(uniq)}
    a = " ".join(x for x in attrs if x)
    return f'<sharedItems {a} count="{len(uniq)}">{body}</sharedItems>'.replace("<sharedItems  ", "<sharedItems "), idx, uniq


def _plain_items(vals):
    nums = [v for v in vals if isinstance(v, (int, float)) and v != ""]
    strs = [v for v in vals if isinstance(v, str) and v != ""]
    blank = any(v in ("", None) for v in vals)
    long_ = any(len(s) > 255 for s in strs)
    attrs = []
    if nums and not strs:
        attrs += ([] if blank else ['containsSemiMixedTypes="0"']) + ['containsString="0"', 'containsNumber="1"',
                                                                      f'minValue="{min(nums)}"', f'maxValue="{max(nums)}"']
    elif nums and strs:
        attrs += ['containsMixedTypes="1"', 'containsNumber="1"', f'minValue="{min(nums)}"', f'maxValue="{max(nums)}"']
    if blank:
        attrs.append('containsBlank="1"')
    if long_:
        attrs.append('longText="1"')
    return f'<sharedItems {" ".join(attrs)}/>'.replace("<sharedItems />", "<sharedItems/>")


def render_xlsx(rows, title, targets, template=None):
    tpl = template or ASSET.read_bytes()
    meta = json.loads(META.read_text(encoding="utf-8"))
    XF = meta["xf"]
    zin = zipfile.ZipFile(io.BytesIO(tpl))
    parts = {n: zin.read(n) for n in zin.namelist()}
    order = zin.namelist()
    T = lambda n: parts[n].decode("utf-8")

    def put(n, s):
        parts[n] = s.encode("utf-8")

    n = len(rows)
    cols = list(zip(*rows)) if rows else [[] for _ in COLUMNS]
    item_idx = {}

    # ── pivot cache definition + records ──
    cd = T("xl/pivotCache/pivotCacheDefinition1.xml")
    fields_xml = []
    for i, name in enumerate(COLUMNS):
        vals = list(cols[i])
        if name in ITEM_FIELDS:
            sx, idx, uniq = _shared_items(vals)
            item_idx[name] = (idx, uniq)
        else:
            sx = _plain_items(vals)
        fields_xml.append(f'<cacheField name="{escape(name)}" numFmtId="0">{sx}</cacheField>')
    cd = re.sub(r"<cacheFields count=\"\d+\">.*?</cacheFields>",
                f'<cacheFields count="{len(COLUMNS)}">' + "".join(fields_xml) + "</cacheFields>", cd, flags=re.S)
    cd = re.sub(r'recordCount="\d+"', f'recordCount="{n}"', cd)
    cd = re.sub(r'refreshedDate="[^"]*"', 'refreshedDate="%.6f"' % ((datetime.now() - datetime(1899, 12, 30)).total_seconds() / 86400), cd)
    put("xl/pivotCache/pivotCacheDefinition1.xml", cd)

    recs = []
    for r in rows:
        out = []
        for i, name in enumerate(COLUMNS):
            v = r[i]
            if name in ITEM_FIELDS:
                k = ("m", "") if v in ("", None) else (("n", v) if isinstance(v, (int, float)) else ("s", str(v)))
                out.append(f'<x v="{item_idx[name][0][k]}"/>')
            elif v in ("", None):
                out.append("<m/>")
            elif isinstance(v, (int, float)):
                out.append(f'<n v="{v}"/>')
            else:
                out.append(f'<s v="{escape(str(v), {chr(34): "&quot;"})}"/>')
        recs.append("<r>" + "".join(out) + "</r>")
    rec_xml = T("xl/pivotCache/pivotCacheRecords1.xml")
    head = rec_xml[:rec_xml.index("<pivotCacheRecords")]
    tag = re.search(r"<pivotCacheRecords[^>]*?(/?)>", rec_xml)
    open_tag = re.sub(r' count="\d+"', "", tag.group(0)).rstrip("/>").rstrip("/") + f' count="{n}">'
    put("xl/pivotCache/pivotCacheRecords1.xml", head + open_tag + "".join(recs) + "</pivotCacheRecords>")

    # ── pivot tables: field items follow the new shared items; layout rebuilt by Excel on open ──
    ncyc = len([k for k in item_idx["CYC"][1] if k[0] != "m"]) or 1
    ncat = len(item_idx["CAT ALLO"][1]) or 1
    pt1_end = 3 + ncyc * 5 + 4
    pt4_top = max(115, pt1_end + 6)
    pt4_end = pt4_top + ncyc + 1
    pt6_top = max(135, pt4_end + 4)
    pt6_end = pt6_top + 3 + ncat * 5 + 4
    for pn in [p for p in parts if re.match(r"xl/pivotTables/pivotTable\d+\.xml$", p)]:
        x = T(pn)
        ptname = re.search(r' name="([^"]+)"', x).group(1)
        pfs = list(re.finditer(r"<pivotField\b[^>]*?(?:/>|>.*?</pivotField>)", x, re.S))
        new = []
        for i, m in enumerate(pfs):
            pf = m.group(0)
            fname = COLUMNS[i] if i < len(COLUMNS) else ""
            if "<items" in pf and fname in item_idx:
                idx, uniq = item_idx[fname]
                collapse = None
                if fname == "PAID/UNPAID" and 'axis="axisCol"' in pf:
                    collapse = "PAID" if ptname == "PivotTable11" else "UNPAID"
                its = []
                for k_i, k in enumerate(uniq):
                    sd = ' sd="0"' if (collapse and k == ("s", collapse)) else ""
                    its.append(f'<item x="{k_i}"{sd}/>')
                if 'defaultSubtotal="0"' not in pf:
                    its.append('<item t="default"/>')
                pf = re.sub(r"<items count=\"\d+\">.*?</items>", f'<items count="{len(its)}">' + "".join(its) + "</items>", pf, flags=re.S)
            new.append(pf)
        out, last = [], 0
        for m, pf in zip(pfs, new):
            out.append(x[last:m.start()]); out.append(pf); last = m.end()
        out.append(x[last:])
        x = "".join(out)
        x = re.sub(r'<rowItems count="\d+">.*?</rowItems>', "", x, flags=re.S)
        x = re.sub(r'<colItems count="\d+">.*?</colItems>', "", x, flags=re.S)
        x = re.sub(r'(<pageField [^>]*?) item="\d+"', r"\1", x)
        if ptname == "PivotTable1":
            x = re.sub(r'<location ref="[^"]+"', f'<location ref="A1:F{pt1_end}"', x)
        elif ptname == "PivotTable4":
            x = re.sub(r'<location ref="[^"]+"', f'<location ref="A{pt4_top}:B{pt4_end}"', x)
        elif ptname == "PivotTable6":
            x = re.sub(r'<location ref="[^"]+"', f'<location ref="A{pt6_top}:F{pt6_end}"', x)
        put(pn, x)

    # ── slicers: every value selectable ──
    for sn in [p for p in parts if p.startswith("xl/slicerCaches/") and p.endswith(".xml")]:
        x = T(sn)
        src = re.search(r'sourceName="([^"]+)"', x).group(1)
        if src in item_idx:
            uniq = item_idx[src][1]
            items = "".join(f'<i x="{k}" s="1"/>' for k in range(len(uniq)))
            x = re.sub(r"<items count=\"\d+\">.*?</items>|<items count=\"\d+\"/>",
                       f'<items count="{len(uniq)}">{items}</items>' if uniq else '<items count="0"/>', x, flags=re.S)
        put(sn, x)

    # ── MAIN sheet + table ──
    main = T("xl/worksheets/sheet2.xml")
    hdr = "".join(_cell(f"{_col(j + 1)}1", h, XF["h_navy"] if j < 4 else XF["h_blue"]) for j, h in enumerate(COLUMNS))
    body = [f'<row r="1" ht="30" customHeight="1">{hdr}</row>']
    for i, r in enumerate(rows, start=2):
        z = (i % 2 == 1)
        cells = []
        for j, v in enumerate(r):
            name = COLUMNS[j]
            if name == "PAID/UNPAID":
                s = XF["m_paid"] if v == "PAID" else XF["m_unpaid"]
            elif name in MONEY:
                s = XF["m_rup_z" if z else "m_rup"]
            elif isinstance(v, (int, float)):
                s = XF["m_num_z" if z else "m_num"]
            else:
                s = XF["m_txt_z" if z else "m_txt"]
            cells.append(_cell(f"{_col(j + 1)}{i}", v, s))
        body.append(f'<row r="{i}">' + "".join(cells) + "</row>")
    last_row = max(n + 1, 2)
    main = re.sub(r"<sheetData>.*?</sheetData>|<sheetData/>", "<sheetData>" + "".join(body) + "</sheetData>", main, flags=re.S)
    main = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:{_col(len(COLUMNS))}{last_row}"/>', main)
    main = re.sub(r"<sheetViews>.*?</sheetViews>", '<sheetViews><sheetView workbookViewId="0"><pane xSplit="2" ySplit="1" '
                  'topLeftCell="C2" activePane="bottomRight" state="frozen"/><selection pane="bottomRight" activeCell="C2" '
                  'sqref="C2"/></sheetView></sheetViews>', main, flags=re.S)
    main = re.sub(r"<conditionalFormatting.*?</conditionalFormatting>", "", main, flags=re.S)
    put("xl/worksheets/sheet2.xml", main)
    tb = T("xl/tables/table1.xml")
    ref = f"A1:{_col(len(COLUMNS))}{last_row}"
    tb = re.sub(r'(<table [^>]*?)ref="[^"]+"', rf'\1ref="{ref}"', tb, count=1)
    tb = re.sub(r'<autoFilter ref="[^"]+"', f'<autoFilter ref="{ref}"', tb)
    tb = re.sub(r' totalsRowCount="\d+"', "", tb)
    put("xl/tables/table1.xml", tb)

    # ── MIS sheet: pivots draw themselves; we write the two FOS TARGET tables + target list ──
    mis = T("xl/worksheets/sheet1.xml")
    fos = sorted({r[CI["FOS NAME"]] for r in rows}, key=lambda s: s.upper())
    cycles = sorted({r[CI["CYC"]] for r in rows if r[CI["CYC"]] != ""}, key=lambda v: (isinstance(v, str), v))
    cellrows = {}

    def add(ref, xml):
        rr = int(re.sub(r"[A-Z]", "", ref))
        cellrows.setdefault(rr, []).append((_colnum(re.sub(r"\d", "", ref)), xml))

    HEAD = ["COUNT", "UNPAID", "PAID", "ENR", "TARGET %", "TARGET ENR", "ACHIEVED %", "ACHIEVED ENR", "PENDING VISIT", "CASH COLL"]
    HSTY = ["h_blue", "h_red", "h_green", "h_blue", "h_amber", "h_amber", "h_green", "h_green", "h_slate", "h_sky"]
    BODY = ["int", "int", "int", "rup", "tgt", "rup", "pct", "rup", "int", "rup"]
    TOTS = ["t_int", "t_int", "t_int", "t_rup", "t_tgt", "t_rup", "t_pct", "t_rup", "t_int", "t_rup"]
    TL = "$GQ$4:$GR$2000"           # target list (FOS → target %)

    # FOS TARGET — ALL (follows the slicers; pulls each figure from the pivots by FOS name)
    c0 = _colnum("AG")
    add("AG2", _cell("AG2", "FOS TARGET — ALL CYCLES (follows the slicers)", XF["title"]))
    for j in range(1, 11):
        add(f"{_col(c0 + j)}2", _cell(f"{_col(c0 + j)}2", "", XF["title"]))
    add("AG3", _cell("AG3", "EMP NAME", XF["h_navy"]))
    for j, h in enumerate(HEAD):
        add(f"{_col(c0 + 1 + j)}3", _cell(f"{_col(c0 + 1 + j)}3", h, XF[HSTY[j]]))
    nrows = max(len(fos), 1) + 1
    first, lastr = 4, 3 + nrows
    for r in range(first, lastr + 1):
        tot = r == lastr
        nm = f"$AG{r}"
        gt = f'OR({nm}="Grand Total",{nm}="Total Result")'
        g = lambda df, ref, extra="": (f'IFERROR(IF({gt},GETPIVOTDATA("{df}",{ref}{extra}),'
                                       f'GETPIVOTDATA("{df}",{ref},"FOS NAME",{nm}{extra})),0)')
        wrap = lambda e: f'IF({nm}="","",{e})'
        f = [
            f'IF(K{r}="","",K{r})',
            wrap(g("COUNT.", "$K$1")),
            wrap(g("COUNT.", "$K$1", ',"PAID/UNPAID","UNPAID"')),
            wrap(g("COUNT.", "$K$1", ',"PAID/UNPAID","PAID"')),
            wrap(g("ENR.", "$K$1")),
            wrap(f'IF({gt},IFERROR(AM{r}/AK{r},{DEFAULT_TARGET}),IFERROR(VLOOKUP({nm},{TL},2,0),{DEFAULT_TARGET}))'),
            wrap(f'IF({gt},SUM(AM${first}:AM{r - 1}),AK{r}*AL{r})') if r > first else wrap(f"AK{r}*AL{r}"),
            wrap(f"IFERROR(AO{r}/AK{r},0)"),
            wrap(g("ENR.", "$K$1", ',"PAID/UNPAID","PAID"')),
            wrap(g("COUNT.", "$V$2", ',"VISITS","NOT VISITED"')),
            wrap(g("Sum of AMOUNT", "$AC$3")),
        ]
        for j, formula in enumerate(f):
            ref = f"{_col(c0 + j)}{r}"
            sty = XF[("t_name" if tot else "name") if j == 0 else (TOTS if tot else BODY)[j - 1]]
            add(ref, _fcell(ref, formula, sty))

    # FOS TARGET — SELECTED CYCLE (yellow cell AW2: ALL or a cycle) — straight from MAIN
    c1 = _colnum("AT")
    add("AT2", _cell("AT2", "FOS TARGET — CYCLE ▸", XF["title"]))
    for j in (1, 2):
        add(f"{_col(c1 + j)}2", _cell(f"{_col(c1 + j)}2", "", XF["title"]))
    default_sel = "ALL"
    add("AW2", _cell("AW2", default_sel, XF["sel"]))
    add("AX2", _cell("AX2", "◂ choose ALL or a cycle", XF["title"]))
    for j in range(5, 11):
        if c1 + j != _colnum("AX"):
            add(f"{_col(c1 + j)}2", _cell(f"{_col(c1 + j)}2", "", XF["title"]))
    add("AT3", _cell("AT3", "EMP NAME", XF["h_navy"]))
    for j, h in enumerate(HEAD):
        add(f"{_col(c1 + 1 + j)}3", _cell(f"{_col(c1 + 1 + j)}3", h, XF[HSTY[j]]))
    cyc_ok = '((($AW$2="ALL")+((Table1[CYC]&"")=($AW$2&"")))>0)'
    for i, name in enumerate(fos + ["Grand Total"]):
        r = 4 + i
        tot = name == "Grand Total"
        add(f"AT{r}", _cell(f"AT{r}", name, XF["t_name" if tot else "name"]))
        if tot:
            fs = [f"SUM({L}4:{L}{r - 1})" for L in ("AU", "AV", "AW", "AX")]
            fs += [f"IFERROR(AZ{r}/AX{r},{DEFAULT_TARGET})", f"SUM(AZ4:AZ{r - 1})", f"IFERROR(BB{r}/AX{r},0)",
                   f"SUM(BB4:BB{r - 1})", f"SUM(BC4:BC{r - 1})", f"SUM(BD4:BD{r - 1})"]
        else:
            cond = f"(Table1[FOS NAME]=$AT{r})*{cyc_ok}"
            fs = [f"SUMPRODUCT({cond})",
                  f'SUMPRODUCT({cond}*(Table1[PAID/UNPAID]="UNPAID"))',
                  f'SUMPRODUCT({cond}*(Table1[PAID/UNPAID]="PAID"))',
                  f"SUMPRODUCT({cond}*Table1[ENR])",
                  f"IFERROR(VLOOKUP($AT{r},{TL},2,0),{DEFAULT_TARGET})",
                  f"AX{r}*AY{r}",
                  f"IFERROR(BB{r}/AX{r},0)",
                  f'SUMPRODUCT({cond}*(Table1[PAID/UNPAID]="PAID")*Table1[ENR])',
                  f'SUMPRODUCT({cond}*(Table1[VISITS]="NOT VISITED"))',
                  f"SUMPRODUCT({cond}*Table1[AMOUNT])"]
        for j, formula in enumerate(fs):
            ref = f"{_col(c1 + 1 + j)}{r}"
            add(ref, _fcell(ref, formula, XF[(TOTS if tot else BODY)[j]]))

    # target list (85% unless set) — used by both target tables
    add("GQ3", _cell("GQ3", "FOS (target list)", XF["h_navy"]))
    add("GR3", _cell("GR3", "TARGET %", XF["h_amber"]))
    for i, name in enumerate(fos):
        add(f"GQ{4 + i}", _cell(f"GQ{4 + i}", name, XF["name"]))
        add(f"GR{4 + i}", _cell(f"GR{4 + i}", float(targets.get(name, DEFAULT_TARGET)), XF["tgt"]))

    rows_xml = []
    for rr in sorted(cellrows):
        cs = "".join(x for _, x in sorted(cellrows[rr]))
        extra = ' ht="32" customHeight="1"' if rr == 3 else (' ht="22" customHeight="1"' if rr == 2 else "")
        rows_xml.append(f'<row r="{rr}"{extra}>{cs}</row>')
    mis = re.sub(r"<sheetData>.*?</sheetData>|<sheetData/>", "<sheetData>" + "".join(rows_xml) + "</sheetData>", mis, flags=re.S)
    mis = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:GR{max(lastr, 4 + len(fos), pt6_end)}"/>', mis)
    # only the %-colour scales on pivot areas survive; old rules on the target area go
    mis = re.sub(r"<conditionalFormatting (?!pivot=)[^>]*>.*?</conditionalFormatting>", "", mis, flags=re.S)
    dv_list = ",".join(["ALL"] + [str(c) for c in cycles])[:250]
    dv = (f'<dataValidations count="1"><dataValidation type="list" allowBlank="1" showInputMessage="1" '
          f'promptTitle="Cycle" prompt="Pick ALL or one cycle" sqref="AW2"><formula1>"{escape(dv_list)}"</formula1>'
          f'</dataValidation></dataValidations>')
    mis = re.sub(r"<dataValidations.*?</dataValidations>", "", mis, flags=re.S)
    anchor = re.search(r"<(hyperlinks|printOptions|pageMargins)\b", mis)
    mis = mis[:anchor.start()] + dv + mis[anchor.start():]
    put("xl/worksheets/sheet1.xml", mis)

    # both sheets now use inline strings → empty the shared-string table (no stale data left behind)
    if "xl/sharedStrings.xml" in parts:
        sst = T("xl/sharedStrings.xml")
        put("xl/sharedStrings.xml", re.sub(r"<sst ([^>]*?)(?: count=\"\d+\")?(?: uniqueCount=\"\d+\")?>.*</sst>",
                                           lambda m: f'<sst {m.group(1)} count="0" uniqueCount="0"/>', sst, flags=re.S))

    # ── workbook: recalc formulas on open; title ──
    wbx = T("xl/workbook.xml")
    if "fullCalcOnLoad" not in wbx:
        wbx = re.sub(r"<calcPr ", '<calcPr fullCalcOnLoad="1" ', wbx, count=1)
    put("xl/workbook.xml", wbx)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for nme in order:
            if nme in parts:
                zo.writestr(nme, parts[nme])
    return out.getvalue()
