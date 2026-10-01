from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, date, timezone
import io

from .. import models
from ..database import get_db
from ..deps import require_roles
from ..excel_io import import_workbook, record_to_case_kwargs, export_cases
from ..allocation import run_allocation
from .. import audit, closing

router = APIRouter(prefix="/api/import", tags=["import"])


def _parse_due(val):
    """Best-effort parse of a due-date cell (date object or many string formats)."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Team-lead upload guard ──────────────────────────────────────────────────────
# A team lead may upload a portfolio file in the HO format (TL / caller / FOS ID per row),
# but ONLY the rows whose TEAM-LEAD id is the uploader's own may be committed — a TL can't
# hand work to another team. HO/admin/backend upload with no such restriction.

def _tl_maps(db: Session):
    """Resolve a sheet's team-lead cell to a user: by emp_code (pure team leads) or by
    tl_emp_code (dual-role caller/FOS granted the team-lead hat), plus a name fallback."""
    users = db.query(models.User).all()
    tls = [u for u in users if u.role == "teamlead" or getattr(u, "also_team_lead", False)]
    by_code = {}
    for u in tls:
        if u.role == "teamlead" and u.emp_code:
            by_code[u.emp_code.strip().upper()] = u
        if getattr(u, "also_team_lead", False) and getattr(u, "tl_emp_code", None):
            by_code[u.tl_emp_code.strip().upper()] = u
    by_name = {u.name.strip().upper(): u for u in tls if u.name}
    return by_code, by_name


def _actor_tl_ids(actor: models.User) -> set:
    """The identifier(s) that mark a case row as belonging to THIS team lead: their name,
    their TL emp_code (pure lead) and/or their second tl_emp_code (dual-role lead)."""
    ids = set()
    if actor.name:
        ids.add(actor.name.strip().upper())
    primary = getattr(actor, "_primary_role", None) or actor.role
    if primary == "teamlead" and actor.emp_code:      # a pure lead's emp_code IS their TL id
        ids.add(actor.emp_code.strip().upper())
    if getattr(actor, "tl_emp_code", None):           # dual-role lead's separate TL id
        ids.add(actor.tl_emp_code.strip().upper())
    return ids


def _is_restricted_uploader(actor: models.User) -> bool:
    """True when the uploader is acting as a team lead (pure, or a dual-role user whose
    current login view is 'teamlead') — so the per-row TL restriction applies."""
    return actor.role == "teamlead"


def _row_tl_user(rec, by_code, by_name):
    """Resolve one sheet row to its team lead: the TEAM-LEAD column first, then any known TL
    emp code appearing anywhere in the row (formats without a TL column), then a name match."""
    k = record_to_case_kwargs(rec)
    val = k.get("team_lead")
    if val and str(val).strip():
        key = str(val).strip().upper()
        u = by_code.get(key) or by_name.get(key)
        if u:
            return u
    for cell in (rec.get("_cells") or []):
        u = by_code.get(str(cell).strip().upper())
        if u:
            return u
    return None


def _classify_row_tl(rec, by_code, by_name, actor_ids, actor_id):
    """('mine' | 'other_tl' | 'no_tl', tl_user_or_None) for a row relative to the uploader."""
    u = _row_tl_user(rec, by_code, by_name)
    if u is None:
        return "no_tl", None
    codes = set()
    if u.name:
        codes.add(u.name.strip().upper())
    if u.role == "teamlead" and u.emp_code:
        codes.add(u.emp_code.strip().upper())
    if getattr(u, "tl_emp_code", None):
        codes.add(u.tl_emp_code.strip().upper())
    if u.id == actor_id or (codes & actor_ids):
        return "mine", u
    return "other_tl", u


@router.post("/preview")
async def preview(file: UploadFile = File(...), default_bank: str | None = Form(None),
                  product: str | None = Form(None), segment: str | None = Form(None),
                  admin: models.User = Depends(require_roles("admin", "backend", "headoffice", "teamlead")),
                  db: Session = Depends(get_db)):
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    sample = [record_to_case_kwargs(r) for r in records[:10]]
    for s in sample:
        if default_bank:
            s["bank"] = default_bank
        if product:
            s["product"] = product
        if segment:
            s["segment"] = segment
        for k, v in list(s.items()):        # Decimals -> str for JSON
            if hasattr(v, "quantize"):
                s[k] = str(v)

    # Pre-upload FOS check: list every row whose FOS ID is missing or unknown, WITH the reason,
    # so HR can decide up-front — continue without a FOS (caller-only) or pick a FOS per case.
    _all_u = db.query(models.User).all()
    fos_by_code = {u.emp_code.strip().upper(): u for u in _all_u
                   if u.emp_code and u.role == "fos" and u.is_active}
    # A caller granted the field-agent hat can own field cases via their fos_emp_code — count it
    # here so those rows aren't wrongly flagged as "no FOS".
    for u in _all_u:
        if u.is_active and getattr(u, "also_field_agent", False) and getattr(u, "fos_emp_code", None):
            fos_by_code.setdefault(u.fos_emp_code.strip().upper(), u)
    no_fos, cap = [], 500
    for r in records:
        k = record_to_case_kwargs(r)
        raw = k.get("fos_name")
        val = (str(raw).strip() if raw is not None else "")
        if val and val.upper() in fos_by_code:
            continue                          # FOS resolved by ID — fine
        if len(no_fos) < cap:
            no_fos.append({"account_no": k.get("account_no"),
                           "customer": k.get("customer_name") or k.get("name"),
                           "fos_in_sheet": val or None,
                           "reason": "blank" if not val else "unknown"})
    fos_options = [{"code": u.emp_code, "name": u.name, "branch": u.branch}
                   for u in db.query(models.User)
                   .filter(models.User.role == "fos", models.User.is_active == True)
                   .order_by(models.User.name).all() if u.emp_code]
    # Dual-role callers who also work field cases are valid FOS choices — offer their FO id too.
    fos_options += [{"code": u.fos_emp_code, "name": u.name + " (caller +FOS)", "branch": u.branch}
                    for u in _all_u
                    if u.is_active and getattr(u, "also_field_agent", False) and getattr(u, "fos_emp_code", None)]

    # Team-lead uploader: classify every row's TL id against the uploader's own so the UI can
    # show that only the uploader's-TL rows will import (the rest are dropped on commit).
    tl_scope = {"restricted": False}
    if _is_restricted_uploader(admin):
        by_code, by_name = _tl_maps(db)
        actor_ids = _actor_tl_ids(admin)
        mine = other = none_ = 0
        other_samples, none_samples = [], []
        scap = 200
        for r in records:
            cls, tlu = _classify_row_tl(r, by_code, by_name, actor_ids, admin.id)
            k = record_to_case_kwargs(r)
            row = {"account_no": k.get("account_no"),
                   "customer": k.get("customer_name") or k.get("name")}
            if cls == "mine":
                mine += 1
            elif cls == "other_tl":
                other += 1
                if len(other_samples) < scap:
                    other_samples.append({**row, "team_lead_in_sheet": (tlu.name if tlu else None)})
            else:
                none_ += 1
                if len(none_samples) < scap:
                    none_samples.append(row)
        tl_scope = {
            "restricted": True,
            "uploader": admin.name,
            "mine_count": mine,
            "other_tl_count": other,
            "no_tl_count": none_,
            "will_import": mine,
            "will_drop": other + none_,
            "other_tl_samples": other_samples,
            "no_tl_samples": none_samples,
        }

    return {"sheet": sheet, "total_rows": len(records), "sample": sample,
            "no_fos_rows": no_fos, "no_fos_count": len(no_fos), "no_fos_capped": len(no_fos) >= cap,
            "fos_options": fos_options, "tl_scope": tl_scope}


@router.post("/commit")
async def commit(file: UploadFile = File(...), default_bank: str | None = Form(None),
                 product: str | None = Form(None), segment: str | None = Form(None),
                 branch: str | None = Form(None), auto_allocate: bool = Form(True),
                 year: int | None = Form(None), month: int | None = Form(None),
                 fos_overrides: str | None = Form(None),
                 admin: models.User = Depends(require_roles("admin", "backend", "headoffice", "teamlead")), db: Session = Depends(get_db)):
    content = await file.read()
    # Snap the chosen/typed branch to its canonical spelling so 'kadapa' joins the existing
    # 'KADAPA' portfolio instead of creating a case-duplicate split. New branches pass through.
    if branch and str(branch).strip():
        from .cases import canonical_branch
        branch = canonical_branch(db, branch)
    # HR may assign a FOS to specific cases at upload time (for rows the sheet left blank/unknown).
    # fos_overrides is a JSON map { account_no: FOS emp_code }.
    import json as _json
    try:
        _fos_ov = {str(k).strip(): str(v).strip().upper() for k, v in (_json.loads(fos_overrides or "{}") or {}).items() if v}
    except Exception:
        _fos_ov = {}
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    # Team-lead uploader: keep ONLY the rows whose team-lead id is the uploader's own — a TL may
    # never assign work to another team. Rows for another TL, or with no TL id, are dropped here
    # (reported back as tl_dropped) BEFORE anything is written. HO/admin/backend skip this entirely.
    tl_dropped = None
    if _is_restricted_uploader(admin):
        _tlc, _tln = _tl_maps(db)
        _aids = _actor_tl_ids(admin)
        kept, d_other, d_none = [], 0, 0
        for r in records:
            cls, _ = _classify_row_tl(r, _tlc, _tln, _aids, admin.id)
            if cls == "mine":
                kept.append(r)
            elif cls == "other_tl":
                d_other += 1
            else:
                d_none += 1
        records = kept
        tl_dropped = {"other_tl": d_other, "no_tl": d_none, "total": d_other + d_none,
                      "kept": len(kept)}

    # The month/year picked on the upload form is the authoritative PERIOD this batch
    # belongs to (multiple uploads in a month accumulate into the same period). Falls
    # back to the current IST month if not supplied.
    from datetime import timezone, timedelta
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    yy = int(year) if year else now_ist.year
    mm = int(month) if month else now_ist.month
    period = f"{yy:04d}-{mm:02d}"

    from ..products import custom_closing_type
    def _apply_period(case_obj, rec):
        """Stamp the period + compute the close date from the product's closing rule
        (an admin-defined rule for a custom product wins over the built-in map)."""
        b = default_bank or case_obj.bank
        p = product or case_obj.product
        due = _parse_due((rec.get("_extra") or {}).get("x_due_date"))
        cd, ctype = closing.compute_close(b, p, period,
                                          cyc=(rec.get("cycle") or getattr(case_obj, "cycle", None)),
                                          due_date=due,
                                          force_type=custom_closing_type(db, b, p))
        case_obj.period = period
        case_obj.close_date = cd
        case_obj.closing_type = ctype

    batch = models.ImportBatch(filename=file.filename, bank=default_bank, product=product,
                               sheet=sheet, rows_total=len(records), uploaded_by=admin.id)
    db.add(batch)
    db.flush()

    # Resolve the sheet's CALLER column to a caller: it now carries the caller's ID
    # (emp_code, e.g. TC001) generated at profile creation. Fall back to matching by name
    # for older sheets. When matched we also normalise caller_name to the real name (MIS).
    _users = db.query(models.User).all()
    _by_id = {u.id: u for u in _users}
    # Allocation is by EMPLOYEE ID ONLY (per the user): the CALLER column holds the caller's
    # emp_code (e.g. TC001), the FOS column holds the FOS's emp_code (e.g. FO007). We match the
    # cell strictly to that ID — no name / fuzzy / GPS guessing — so a case is only ever handed
    # to the exact person printed in the sheet. Anything that isn't a known ID is reported back
    # unallocated with a reason, never assigned to someone at random.
    # CALLER column resolves to a TELECALLER's emp_code ONLY (e.g. TC001) — never a team-lead code.
    # A dual-role caller who also holds a TL hat still matches here by their telecaller emp_code
    # (their TL id is used only for the TEAM LEAD column, not the caller column).
    _caller_by_code = {u.emp_code.strip().upper(): u for u in _users
                       if u.emp_code and u.role == "telecaller" and u.is_active}
    _fos_by_code = {u.emp_code.strip().upper(): u for u in _users
                    if u.emp_code and u.role == "fos" and u.is_active}
    # Dual-role staff carry a SECOND id for their other hat: a caller who also works field cases
    # has a field-agent id (fos_emp_code) and a field agent who also calls has a caller id
    # (tc_emp_code). Index those too so a case whose FOS/CALLER column names that second id is
    # attributed to the right person under the right hat.
    for u in _users:
        if not u.is_active:
            continue
        if getattr(u, "also_field_agent", False) and getattr(u, "fos_emp_code", None):
            _fos_by_code.setdefault(u.fos_emp_code.strip().upper(), u)
        if getattr(u, "also_caller", False) and getattr(u, "tc_emp_code", None):
            _caller_by_code.setdefault(u.tc_emp_code.strip().upper(), u)
    # Team lead is resolved from the sheet's TEAM LEAD ID column (its emp code, e.g. TL001,
    # or the TL's name). The resolved TL is stamped on the case and the case's caller + FOS
    # are linked to report to that team lead (so it shows in the team lead's scope).
    # Team leads = real teamlead-role users, PLUS caller/FOS who were granted the team-lead hat
    # (matched by their second team-lead ID, tl_emp_code, or their name).
    _tls = [u for u in _users if u.role == "teamlead" or getattr(u, "also_team_lead", False)]
    _tl_by_code = {}
    for u in _tls:
        if u.role == "teamlead" and u.emp_code:
            _tl_by_code[u.emp_code.strip().upper()] = u
        if getattr(u, "also_team_lead", False) and getattr(u, "tl_emp_code", None):
            _tl_by_code[u.tl_emp_code.strip().upper()] = u
    _tl_by_name = {u.name.strip().upper(): u for u in _tls if u.name}
    _tl_cands = [(u.name.strip().upper(), u) for u in _tls if u.name]

    def _match(val, by_code):
        """Resolve one CALLER/FOS/TL cell to a person by EMPLOYEE ID ONLY, and say WHY if it can't.
        No name or fuzzy matching — that caused wrong / confusing assignments. The cell must
        carry the exact emp_code (e.g. TC001 / FO007 / TL003). Returns (user_or_None, reason):
          '' matched · 'blank' no value in the cell · 'unknown' the ID isn't a known active employee."""
        if val is None or not str(val).strip():
            return None, "blank"
        key = str(val).strip().upper()
        u = by_code.get(key)
        if u:
            return u, ""
        return None, "unknown"

    def _match_caller(val):
        return _match(val, _caller_by_code)

    def _match_fos(val):
        return _match(val, _fos_by_code)

    def _match_teamlead(val):
        return _match(val, _tl_by_code)

    def _resolve_tl(val):
        """Resolve a team-lead cell to a real team-lead user by EMP CODE (TL001 / dual-role
        tl_emp_code) or by NAME. Returns the user or None. Used to decide whether a value is a
        genuine team lead before it's stamped on a case."""
        if val is None or not str(val).strip():
            return None
        key = str(val).strip().upper()
        return _tl_by_code.get(key) or _tl_by_name.get(key)

    def _row_tl_code(rec):
        """Header-agnostic fallback: recognise a known team-lead emp code (e.g. TL001) appearing
        in ANY cell of the row, for formats (like PL/BL) that have no team-lead column.
        GUARD: only a canonical TL### token counts — this stops a stray numeric / short value in an
        unrelated column (cycle, bucket, a count, an account fragment) from being mistaken for a
        team lead, which was silently assigning random team leads to 1–2 cases."""
        for cell in (rec.get("_cells") or []):
            cs = str(cell).strip()
            if not (len(cs) >= 3 and cs[:2].upper() == "TL" and cs[2:].isdigit()):
                continue
            u = _tl_by_code.get(cs.upper())
            if u:
                return u.emp_code or u.name
        return None

    def _resolve_caller(val):
        return _match_caller(val)[0]

    def _resolve_fos(val):
        return _match_fos(val)[0]

    def _apply_teamlead(case_obj, cu, fu):
        """Stamp the team lead on the case, normalising it to the TL's full name. Returns True if a
        real team lead was applied.
        FIX A: if the value doesn't resolve to a genuine team lead (code or name), BLANK it — never
        leave a stray/typo value on the case, so it can't surface as a bogus 'team lead' in MIS.
        FIX C: do NOT overwrite the caller/FOS's reporting team_lead_id from an upload. A shared
        caller/FOS works under different team leads across portfolios; the case's own team_lead is
        the source of truth for team-lead scope (teamlead_case_filter matches on it, not on the
        person's team_lead_id). Overwriting it was re-pointing people to whichever file was uploaded
        last, shuffling 'My Team' rosters."""
        tl = _resolve_tl(case_obj.team_lead)
        if not tl:
            case_obj.team_lead = None
            return False
        case_obj.team_lead = tl.name
        return True

    # Per-row diagnostics: rows whose CALLER/FOS was named on the sheet but didn't map to
    # anyone (typo, person not created yet, or an ambiguous partial name). Blanks are counted
    # but not listed — not every case carries both a caller and a field officer.
    _REASON_TEXT = {"unknown": "not a known employee ID — put the caller/FOS ID (e.g. TC001 / FO007) in this column",
                    "ambiguous": "name matches more than one person — use their ID (e.g. TC001)"}
    unresolved_rows: list = []
    blank_caller = blank_fos = 0
    _UNRESOLVED_CAP = 300

    def _flag(rec_kwargs, field, raw, reason):
        nonlocal blank_caller, blank_fos
        if reason == "blank":
            if field == "caller":
                blank_caller += 1
            else:
                blank_fos += 1
            return
        if len(unresolved_rows) < _UNRESOLVED_CAP:
            unresolved_rows.append({
                "account_no": rec_kwargs.get("account_no"),
                "customer": rec_kwargs.get("customer_name") or rec_kwargs.get("name"),
                "field": field,
                "value_in_sheet": (str(raw).strip() if raw is not None else None),
                "reason": reason,
                "detail": _REASON_TEXT.get(reason, reason),
            })

    imported, skipped = 0, 0
    # Any collection that arrives on the sheet (a non-zero received amount) is logged as a dated
    # PAYMENT event so it shows up in the collections trend / FTD-MTD windows exactly like an
    # in-app payment. Delta-based (new − old) so re-uploading the same file never double-counts.
    _imp_events: list[tuple] = []
    def _num(v):
        try:
            return float(str(v).replace(",", "").strip() or 0)
        except Exception:
            return 0.0
    for rec in records:
        kwargs = record_to_case_kwargs(rec)
        acct = kwargs.get("account_no")
        # A case is unique per ACCOUNT + BANK + PRODUCT + MONTH(period). The same loan number can
        # therefore exist as a separate case under a different bucket/product or a different month —
        # re-uploading the SAME product+month updates in place; a new bucket/month adds fresh cases.
        existing = None
        if acct:
            _mb = default_bank or kwargs.get("bank")
            _mp = product or kwargs.get("product")
            eq = db.query(models.Case).filter(models.Case.account_no == acct,
                                              models.Case.period == period,
                                              models.Case.removed.isnot(True))
            if _mb:
                eq = eq.filter(models.Case.bank == _mb)
            if _mp:
                eq = eq.filter(models.Case.product == _mp)
            existing = eq.first()
        if existing:
            _old_recv = _num(existing.received_amount)
            _old_addr = (existing.address, existing.pincode)
            # update amounts / status, don't duplicate
            for k in ("funding_amount", "received_amount", "pending_amount", "paid_status",
                      "disposition", "remarks", "address", "pincode", "phone",
                      "enr", "norm_amount", "stab_amount", "rollback_amount", "norm_stab",
                      "total_outstanding", "principal_outstanding",
                      "caller_name", "fos_name", "team", "bucket", "cycle", "final_status"):
                if kwargs.get(k) is not None:
                    setattr(existing, k, kwargs[k])
            # If the re-upload changed the address/pincode, this case needs geocoding again —
            # clear the "attempted" marker (and the geocoded pin, unless a FOS verified it in the
            # field) so the next Geocode run picks up the NEW address.
            if (existing.address, existing.pincode) != _old_addr:
                existing.geo_attempted_at = None
                if existing.location_source != "field":
                    existing.latitude = existing.longitude = None
                    existing.location_source = None
            if kwargs.get("extra"):                 # merge new loan/caller columns
                existing.extra = {**(existing.extra or {}), **kwargs["extra"]}
            _rawc = kwargs.get("caller_name")
            cu, _cr = _match_caller(_rawc)
            if cu:
                existing.assigned_caller_id = cu.id
                existing.caller_name = cu.name
            elif not existing.assigned_caller_id:      # still nobody on this case → report why
                _flag(kwargs, "caller", _rawc, _cr)
            _rawf = kwargs.get("fos_name")
            fu, _fr = _match_fos(_rawf)
            if not fu and acct and str(acct) in _fos_ov:      # HR-assigned FOS for this case at upload
                fu = _fos_by_code.get(_fos_ov[str(acct)])
            if fu:
                existing.assigned_fos_id = fu.id
                existing.fos_name = fu.name
                if fu.branch and not branch:            # case's branch = its field owner (FOS) branch
                    existing.branch = fu.branch
            elif not existing.assigned_fos_id:
                _flag(kwargs, "fos", _rawf, _fr)
            # Team lead: header column first, else a canonical TL code found anywhere in the row.
            if not _resolve_tl(existing.team_lead):
                _tlc = _row_tl_code(rec)
                if _tlc:
                    existing.team_lead = _tlc
            _apply_teamlead(existing, cu or _by_id.get(existing.assigned_caller_id),
                            fu or _by_id.get(existing.assigned_fos_id))
            if default_bank:
                existing.bank = default_bank
            if product:
                existing.product = product
            if segment:
                existing.segment = segment
            if branch:                       # allow a re-upload to (re)assign the branch
                existing.branch = branch
                existing.branch_explicit = True   # explicit upload branch → this portfolio splits
            _apply_period(existing, rec)      # re-stamp period + recompute close date
            _dnew = _num(existing.received_amount) - _old_recv
            if _dnew > 0.5:                   # sheet shows more collected than before → dated event
                _imp_events.append((existing, round(_dnew, 2)))
            skipped += 1
            continue
        # This upload is for one bank + product + segment — stamp every new row.
        if default_bank:
            kwargs["bank"] = default_bank
        if product:
            kwargs["product"] = product
        if segment:
            kwargs["segment"] = segment
        if branch:
            kwargs["branch"] = branch
            kwargs["branch_explicit"] = True     # explicit upload branch → this portfolio splits
        _rawc = kwargs.get("caller_name")
        cu, _cr = _match_caller(_rawc)
        if cu:
            kwargs["assigned_caller_id"] = cu.id
            kwargs["caller_name"] = cu.name
        else:
            _flag(kwargs, "caller", _rawc, _cr)
        _rawf = kwargs.get("fos_name")
        fu, _fr = _match_fos(_rawf)
        if not fu and acct and str(acct) in _fos_ov:      # HR-assigned FOS for this case at upload
            fu = _fos_by_code.get(_fos_ov[str(acct)])
        if fu:
            kwargs["assigned_fos_id"] = fu.id
            kwargs["fos_name"] = fu.name
            if fu.branch and not kwargs.get("branch"):   # case's branch = its field owner (FOS) branch
                kwargs["branch"] = fu.branch
        else:
            _flag(kwargs, "fos", _rawf, _fr)
        # Carry over a caller-discovered NEW phone / NEW address from any earlier case with the
        # same account OR card number (a different month/bucket) so the field team can reach the
        # customer straight away. Marked "Imported from database" so it's clear it wasn't on the sheet.
        cardno = kwargs.get("card_no")
        if (not kwargs.get("new_phone") or not kwargs.get("new_address")) and (acct or cardno):
            keyconds = []
            if acct:
                keyconds.append(models.Case.account_no == acct)
            if cardno:
                keyconds.append(models.Case.card_no == cardno)
            prior = (db.query(models.Case)
                     .filter(or_(*keyconds), models.Case.removed.isnot(True),
                             or_(models.Case.new_phone.isnot(None), models.Case.new_address.isnot(None)))
                     .order_by(models.Case.new_contact_at.desc(), models.Case.updated_at.desc())
                     .first())
            if prior:
                pulled = False
                if not kwargs.get("new_phone") and prior.new_phone:
                    kwargs["new_phone"] = prior.new_phone; pulled = True
                if not kwargs.get("new_address") and prior.new_address:
                    kwargs["new_address"] = prior.new_address; pulled = True
                if pulled:
                    kwargs["new_contact_by"] = "Imported from database"
                    kwargs["new_contact_at"] = datetime.now(timezone.utc)
        # Team lead: header column first, else a canonical TL code found anywhere in the row.
        if not _resolve_tl(kwargs.get("team_lead")):
            _tlc = _row_tl_code(rec)
            if _tlc:
                kwargs["team_lead"] = _tlc
        kwargs["import_batch_id"] = batch.id
        new_case = models.Case(**kwargs)
        _apply_teamlead(new_case, cu, fu)     # stamp TL + link caller/FOS to that team lead
        _apply_period(new_case, rec)
        db.add(new_case)
        _rv0 = _num(kwargs.get("received_amount"))
        if _rv0 > 0.5:                        # fresh case already carries a collection → dated event
            _imp_events.append((new_case, round(_rv0, 2)))
        imported += 1

    # Turn every imported collection into a dated PAYMENT event so the trend / FTD-MTD windows
    # count it identically to a caller payment, DPR update, or field collection — no gaps.
    if _imp_events:
        db.flush()                            # assign ids to freshly-added cases
        for _c, _amt in _imp_events:
            _cid = _c.assigned_caller_id or _c.assigned_fos_id
            db.add(models.CallLog(case_id=_c.id, caller_id=_cid,
                                  disposition="PAYMENT", ptp_amount=_amt,
                                  note="Imported collection (from upload)"))

    batch.rows_imported = imported
    batch.rows_skipped = skipped
    audit.record(db, admin, "import", None, entity_type="import",
                 new=str(imported), detail=f"Imported {imported} cases from {file.filename}"
                 + (f" ({default_bank})" if default_bank else ""),
                 meta={"batch_id": batch.id, "bank": default_bank, "sheet": sheet,
                       "rows_total": len(records), "skipped": skipped})
    db.commit()

    # Allocation is EMPLOYEE-ID ONLY (from the sheet's CALLER/FOS ID columns, done above).
    # We deliberately DO NOT run the pincode/GPS/load-balancing auto-allocator here — that
    # would assign cases to people who weren't named in the sheet, which is exactly the
    # "random" behaviour the user asked us to stop. Anything without a valid ID stays
    # unallocated and is reported in assignment_report so it can be fixed and re-uploaded.
    alloc = {"fos_allocated": 0, "caller_allocated": 0}

    # Report the overall assignment state so a repeat upload (0 *new* allocations)
    # isn't mistaken for "nothing is allocated".
    q = db.query(models.Case)
    if default_bank:
        q = q.filter(models.Case.bank == default_bank)
    total_cases = q.count()
    assigned_fos = q.filter(models.Case.assigned_fos_id.isnot(None)).count()
    assigned_caller = q.filter(models.Case.assigned_caller_id.isnot(None)).count()

    # Post-commit assignment report: which named rows couldn't be mapped, and why.
    unresolved_caller = sum(1 for r in unresolved_rows if r["field"] == "caller")
    unresolved_fos = sum(1 for r in unresolved_rows if r["field"] == "fos")
    assignment_report = {
        "unresolved_caller": unresolved_caller,
        "unresolved_fos": unresolved_fos,
        "blank_caller": blank_caller,
        "blank_fos": blank_fos,
        "capped": len(unresolved_rows) >= _UNRESOLVED_CAP,
        "rows": unresolved_rows,
    }

    return {"sheet": sheet, "imported": imported, "updated": skipped,
            "total": len(records), "allocation": alloc,
            "total_cases": total_cases,
            "assigned_fos_total": assigned_fos,
            "assigned_caller_total": assigned_caller,
            "assignment_report": assignment_report,
            "tl_dropped": tl_dropped,
            "batch_id": batch.id}


@router.get("/batches")
def recent_batches(limit: int = 40, db: Session = Depends(get_db),
                   admin: models.User = Depends(require_roles("admin", "headoffice"))):
    """Recent portfolio uploads, newest first — so admin/head office can undo a wrong upload.
    live = cases from this upload still active (not already removed); removed = already pulled out."""
    from sqlalchemy import func
    rows = (db.query(models.ImportBatch)
            .order_by(models.ImportBatch.created_at.desc()).limit(limit).all())
    names = {u.id: u.name for u in db.query(models.User).all()}
    # counts per batch (live vs removed) in two grouped queries
    live = dict(db.query(models.Case.import_batch_id, func.count(models.Case.id))
                .filter(models.Case.import_batch_id.isnot(None), models.Case.removed.isnot(True))
                .group_by(models.Case.import_batch_id).all())
    gone = dict(db.query(models.Case.import_batch_id, func.count(models.Case.id))
                .filter(models.Case.import_batch_id.isnot(None), models.Case.removed.is_(True))
                .group_by(models.Case.import_batch_id).all())
    return [{
        "id": b.id, "filename": b.filename, "bank": b.bank, "product": b.product,
        "rows_total": b.rows_total, "rows_imported": b.rows_imported,
        "uploaded_by": names.get(b.uploaded_by) or "—",
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "live": int(live.get(b.id, 0)), "removed": int(gone.get(b.id, 0)),
    } for b in rows]


@router.post("/batches/{batch_id}/delete")
def delete_batch(batch_id: int, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "headoffice"))):
    """Undo a whole upload: soft-remove every case that came in on this batch (reversible via
    the Removed-cases bin). Use when a wrong file was uploaded to a portfolio."""
    from datetime import datetime, timezone
    batch = db.query(models.ImportBatch).filter(models.ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Upload not found")
    rows = (db.query(models.Case)
            .filter(models.Case.import_batch_id == batch_id, models.Case.removed.isnot(True)).all())
    now = datetime.now(timezone.utc)
    banks = set()
    for c in rows:
        c.removed = True
        c.removed_at = now
        c.removed_by = actor.id
        c.allocation_reason = f"Upload undone (#{batch_id})"
        audit.stamp_case(c, actor)
        banks.add((c.bank, c.product))
    audit.record(db, actor, "delete", None, entity_type="import",
                 detail=f"Undid upload #{batch_id} ({batch.filename or ''}) — {len(rows)} cases removed",
                 meta={"batch_id": batch_id, "count": len(rows),
                       "bank": batch.bank, "product": batch.product})
    db.commit()
    from .realtime import notify_data_changed
    for bank, product in banks:
        notify_data_changed(bank, product)
    return {"batch_id": batch_id, "removed": len(rows)}


@router.get("/export")
def export(db: Session = Depends(get_db), admin: models.User = Depends(require_roles("admin", "backend", "headoffice"))):
    data = export_cases(db)
    audit.record(db, admin, "download", None, entity_type="download",
                 detail="Downloaded full recovery tracker export (Excel)")
    db.commit()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SSD_Recovery_Tracker.xlsx"},
    )
