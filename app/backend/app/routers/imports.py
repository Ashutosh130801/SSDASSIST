from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, date, timezone
import io

from .. import models
from ..database import get_db
from ..deps import require_roles
from ..excel_io import import_workbook, record_to_case_kwargs, export_cases, HEADER_MAP
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


@router.get("/portfolios")
def list_portfolios(actor: models.User = Depends(require_roles("admin", "headoffice")),
                    db: Session = Depends(get_db)):
    """Month-wise list of portfolios (period → bank/product/branch with a case count) so the
    admin/HO can pick exactly which portfolio an update/correction file applies to before uploading."""
    from sqlalchemy import func as _f
    rows = (db.query(models.Case.period, models.Case.bank, models.Case.product, models.Case.branch,
                     _f.count(models.Case.id))
            .filter(models.Case.removed.isnot(True))
            .group_by(models.Case.period, models.Case.bank, models.Case.product, models.Case.branch)
            .all())
    # Merge branches that differ only by CASE/whitespace (e.g. "Visakhapatnam" vs "VISAKHAPATNAM")
    # into ONE portfolio, so a single correction/backfill file covers both. The scope endpoints
    # already match branch case-insensitively, so the chosen display label updates every variant.
    merged = {}
    for (p, b, pr, br, n) in rows:
        key = (p or "—", b or "—", pr or "—", (br or "").strip().lower())
        if key not in merged:
            merged[key] = {"period": p or "—", "bank": b or "—", "product": pr or "—",
                           "branch": (br or "").strip(), "count": 0, "_variants": {}}
        merged[key]["count"] += int(n)
        v = (br or "").strip()
        if v:
            merged[key]["_variants"][v] = merged[key]["_variants"].get(v, 0) + int(n)
    out = []
    for m in merged.values():
        # Display the variant that has the most cases (the one people actually use most).
        if m["_variants"]:
            m["branch"] = max(m["_variants"].items(), key=lambda kv: kv[1])[0]
        m.pop("_variants", None)
        out.append(m)
    # newest month first, then bank/product
    out.sort(key=lambda x: (x["period"], x["bank"], x["product"], x["branch"]), reverse=True)
    return {"portfolios": out}


_BACKFILL_ADDR_FIELDS = ("address", "address2", "address3", "pincode", "pincode2", "pincode3")


def _bf_norm(v):
    return (str(v).strip() or None) if v not in (None, "") else None


@router.post("/backfill-addresses")
async def backfill_addresses(
        file: UploadFile = File(...),
        default_bank: str | None = Form(None),
        commit: bool = Form(False),
        scope_bank: str | None = Form(None),
        scope_product: str | None = Form(None),
        scope_branch: str | None = Form(None),
        scope_period: str | None = Form(None),
        actor: models.User = Depends(require_roles("admin", "headoffice")),
        db: Session = Depends(get_db)):
    """Re-read an ORIGINAL portfolio file and fill ONLY the 2nd/3rd address lines + their pincodes
    onto cases that already exist. Nothing else is touched — money, allocation, dispositions,
    payments and history stay as they are. Matches by account_no (+ bank + product when present),
    across all non-removed months. Any address line that changes is re-armed for geocoding so the
    next Geocode run pins it. Pass commit=false first for a dry run (default)."""
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    rows_with_extra = matched = changed_cases = unmatched = 0
    field_changes = {f: 0 for f in _BACKFILL_ADDR_FIELDS}
    for rec in records:
        k = record_to_case_kwargs(rec)
        acct = _bf_norm(k.get("account_no"))
        if not acct:
            continue
        # Skip rows that carry no new address data at all.
        if not any(_bf_norm(k.get(f)) for f in ("address2", "address3", "pincode2", "pincode3")):
            continue
        rows_with_extra += 1
        q = db.query(models.Case).filter(models.Case.account_no == acct,
                                         models.Case.removed.isnot(True))
        # A chosen portfolio scope (period/bank/product/branch) wins over the file's own columns,
        # so an update file is confined to exactly the portfolio the admin picked.
        bank = _bf_norm(scope_bank) or _bf_norm(k.get("bank")) or _bf_norm(default_bank)
        prod = _bf_norm(scope_product) or _bf_norm(k.get("product"))
        if bank:
            q = q.filter(models.Case.bank == bank)
        if prod:
            q = q.filter(models.Case.product == prod)
        if _bf_norm(scope_period):
            q = q.filter(models.Case.period == _bf_norm(scope_period))
        if _bf_norm(scope_branch):
            from sqlalchemy import func as _f
            q = q.filter(_f.lower(_f.trim(models.Case.branch)) == _bf_norm(scope_branch).lower())
        cases = q.all()
        if not cases:
            unmatched += 1
            continue
        for cs in cases:
            matched += 1
            touched = False
            old_a2 = (cs.address2, cs.pincode2)
            old_a3 = (cs.address3, cs.pincode3)
            for f in _BACKFILL_ADDR_FIELDS:
                newv = _bf_norm(k.get(f))
                if newv and _bf_norm(getattr(cs, f, None)) != newv:
                    setattr(cs, f, newv)
                    field_changes[f] += 1
                    touched = True
            if touched:
                changed_cases += 1
                if (cs.address2, cs.pincode2) != old_a2:
                    cs.latitude2 = cs.longitude2 = cs.geo_precision2 = None
                    cs.geo_attempted_at = None
                if (cs.address3, cs.pincode3) != old_a3:
                    cs.latitude3 = cs.longitude3 = cs.geo_precision3 = None
                    cs.geo_attempted_at = None

    if commit and changed_cases:
        audit.record(db, actor, "backfill_addresses", entity_type="import",
                     detail=f"{file.filename}: {changed_cases} cases updated (sheets: {sheet})")
        db.commit()
    else:
        db.rollback()

    return {"committed": bool(commit and changed_cases), "file": file.filename, "sheet": sheet,
            "rows_in_file": len(records), "rows_with_extra_address": rows_with_extra,
            "cases_matched": matched, "cases_changed": changed_cases,
            "rows_no_match": unmatched, "field_changes": field_changes}


# ── Re-link allocation ───────────────────────────────────────────────────────────
# Some already-imported cases never got linked to a FOS / caller account: the sheet carried the
# person's EMP CODE (e.g. FO048 / TC012) OR their full NAME, but at the moment of that upload the
# account didn't exist yet, was inactive, or wasn't the right role — so only the raw text was stored
# (assigned_*_id null). Such cases are invisible to that officer's app (My Cases scopes by
# assigned_fos_id) and split off in the MIS ranking. This re-links any orphan whose stored
# fos_name / caller_name text is an exact active employee CODE, and (as a fallback) an exact full
# NAME — but a name shared by two or more active accounts is skipped, so a name can never mis-assign.
def _relink_code_maps(db):
    """Resolvers for FOS and caller: try exact EMP CODE first (incl. dual-role second ids), then
    exact full NAME. Returns (resolve_fos, resolve_caller); each takes the raw cell text and returns
    a user or None. Names that map to >1 active account are dropped from the name index."""
    users = db.query(models.User).all()
    fos_code, caller_code = {}, {}
    fos_name_hits, caller_name_hits = {}, {}      # NAME -> set(user ids), to detect duplicates
    fos_name, caller_name = {}, {}
    for u in users:
        if not u.is_active:
            continue
        code = (u.emp_code or "").strip().upper()
        nm = (u.name or "").strip().upper()
        if code and u.role == "fos":
            fos_code[code] = u
        if code and u.role == "telecaller":
            caller_code[code] = u
        if getattr(u, "also_field_agent", False) and getattr(u, "fos_emp_code", None):
            fos_code.setdefault(u.fos_emp_code.strip().upper(), u)
        if getattr(u, "also_caller", False) and getattr(u, "tc_emp_code", None):
            caller_code.setdefault(u.tc_emp_code.strip().upper(), u)
        # NAME index — a FOS (or field-hatted caller) can own field cases; a caller (or
        # call-hatted FOS) can own calling cases. Track every account that answers to a name.
        if nm:
            if u.role == "fos" or getattr(u, "also_field_agent", False):
                fos_name_hits.setdefault(nm, set()).add(u.id)
                fos_name[nm] = u
            if u.role == "telecaller" or getattr(u, "also_caller", False):
                caller_name_hits.setdefault(nm, set()).add(u.id)
                caller_name[nm] = u
    # Drop any name shared by 2+ active accounts — ambiguous, never auto-linked.
    for nm, ids in fos_name_hits.items():
        if len(ids) > 1:
            fos_name.pop(nm, None)
    for nm, ids in caller_name_hits.items():
        if len(ids) > 1:
            caller_name.pop(nm, None)

    def _resolve_fos(raw):
        key = str(raw or "").strip().upper()
        return fos_code.get(key) or fos_name.get(key) if key else None

    def _resolve_caller(raw):
        key = str(raw or "").strip().upper()
        return caller_code.get(key) or caller_name.get(key) if key else None

    return _resolve_fos, _resolve_caller


@router.post("/relink-allocation")
def relink_allocation(
        commit: bool = Form(False),
        scope_bank: str | None = Form(None),
        scope_product: str | None = Form(None),
        scope_branch: str | None = Form(None),
        scope_period: str | None = Form(None),
        actor: models.User = Depends(require_roles("admin", "headoffice")),
        db: Session = Depends(get_db)):
    """Link orphan cases to the matching active account — exact employee code first, then exact full
    name (names shared by 2+ accounts are skipped). Repairs cases whose id is NULL *or* points to a
    deleted account (stale link). Pass commit=false for a dry run (default). The dry run also reports
    cases it can't fix (text matches no active account) and cases already linked to a DIFFERENT valid
    account (left untouched), so you can see exactly why something isn't linking. Optional scope."""
    resolve_fos, resolve_caller = _relink_code_maps(db)
    valid_ids = {u.id for u in db.query(models.User.id).all()}
    umap = {u.id: u for u in db.query(models.User).all()}
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    sb, sp = _bf_norm(scope_bank), _bf_norm(scope_product)
    if sb:
        q = q.filter(models.Case.bank == sb)
    if sp:
        q = q.filter(models.Case.product == sp)
    if _bf_norm(scope_period):
        q = q.filter(models.Case.period == _bf_norm(scope_period))
    if _bf_norm(scope_branch):
        from sqlalchemy import func as _f
        q = q.filter(_f.lower(_f.trim(models.Case.branch)) == _bf_norm(scope_branch).lower())
    # Any case that carries a FOS or caller text label is a candidate (we decide per-case whether
    # its current id is missing / stale / valid).
    q = q.filter(or_(models.Case.fos_name.isnot(None), models.Case.caller_name.isnot(None)))

    fos_linked, caller_linked = 0, 0
    fos_unresolved, caller_unresolved = 0, 0          # text present, no active account matches
    fos_mislinked, caller_mislinked = 0, 0            # already linked to a DIFFERENT valid account
    by_person = {}
    samples, unresolved_samples, mislinked_samples = [], [], []
    period_linked = {}                                # period -> count of newly-linked cases

    def _need(cur):
        """True when a case's current id must be (re)linked: it's missing or points to a dead user."""
        return cur is None or cur not in valid_ids

    for cs in q.all():
        # ── FOS ──
        if cs.fos_name:
            cur = cs.assigned_fos_id
            u = resolve_fos(cs.fos_name)
            if _need(cur):
                if u:
                    if commit:
                        cs.assigned_fos_id = u.id
                        cs.fos_name = u.name
                        if u.branch and not (cs.branch or "").strip():
                            cs.branch = u.branch
                    fos_linked += 1
                    period_linked[cs.period or "—"] = period_linked.get(cs.period or "—", 0) + 1
                    by_person[f"FOS {u.emp_code} · {u.name}"] = by_person.get(f"FOS {u.emp_code} · {u.name}", 0) + 1
                    if len(samples) < 50:
                        samples.append({"account_no": cs.account_no, "role": "FOS", "period": cs.period,
                                        "was": cs.fos_name, "linked_to": f"{u.name} ({u.emp_code})"})
                else:
                    fos_unresolved += 1
                    if len(unresolved_samples) < 30:
                        unresolved_samples.append({"account_no": cs.account_no, "role": "FOS", "text": cs.fos_name})
            elif u and u.id != cur:                   # already on a valid but different account
                fos_mislinked += 1
                if len(mislinked_samples) < 30:
                    cu = umap.get(cur)
                    mislinked_samples.append({"account_no": cs.account_no, "role": "FOS", "text": cs.fos_name,
                                              "currently": f"{cu.name} ({cu.emp_code})" if cu else f"#{cur}",
                                              "text_matches": f"{u.name} ({u.emp_code})"})
        # ── Caller ──
        if cs.caller_name:
            cur = cs.assigned_caller_id
            u = resolve_caller(cs.caller_name)
            if _need(cur):
                if u:
                    if commit:
                        cs.assigned_caller_id = u.id
                        cs.caller_name = u.name
                    caller_linked += 1
                    by_person[f"Caller {u.emp_code} · {u.name}"] = by_person.get(f"Caller {u.emp_code} · {u.name}", 0) + 1
                    if len(samples) < 50:
                        samples.append({"account_no": cs.account_no, "role": "Caller", "period": cs.period,
                                        "was": cs.caller_name, "linked_to": f"{u.name} ({u.emp_code})"})
                else:
                    caller_unresolved += 1
                    if len(unresolved_samples) < 30:
                        unresolved_samples.append({"account_no": cs.account_no, "role": "Caller", "text": cs.caller_name})
            elif u and u.id != cur:
                caller_mislinked += 1
                if len(mislinked_samples) < 30:
                    cu = umap.get(cur)
                    mislinked_samples.append({"account_no": cs.account_no, "role": "Caller", "text": cs.caller_name,
                                              "currently": f"{cu.name} ({cu.emp_code})" if cu else f"#{cur}",
                                              "text_matches": f"{u.name} ({u.emp_code})"})

    if commit and (fos_linked or caller_linked):
        audit.record(db, actor, "relink_allocation", entity_type="import",
                     detail=f"re-link (code+name): {fos_linked} FOS + {caller_linked} caller "
                            f"(scope: {sb or 'all'}/{sp or 'all'}/{_bf_norm(scope_branch) or 'all'}/{_bf_norm(scope_period) or 'all'})")
        db.commit()
    else:
        db.rollback()

    return {"committed": bool(commit and (fos_linked or caller_linked)),
            "fos_linked": fos_linked, "caller_linked": caller_linked,
            "fos_unresolved": fos_unresolved, "caller_unresolved": caller_unresolved,
            "fos_mislinked": fos_mislinked, "caller_mislinked": caller_mislinked,
            "period_linked": sorted([{"period": k, "count": v} for k, v in period_linked.items()],
                                    key=lambda x: str(x["period"])),
            "by_person": sorted([{"who": k, "count": v} for k, v in by_person.items()],
                                key=lambda x: -x["count"]),
            "samples": samples,
            "unresolved_samples": unresolved_samples,
            "mislinked_samples": mislinked_samples}


# ── Corrections upload ──────────────────────────────────────────────────────────
# Re-upload a CORRECTED copy of the ORIGINAL portfolio/case file to fix columns that were wrong in
# the first upload — WITHOUT deleting the portfolio and losing all the calling/visit/payment progress
# on it. The admin/HO picks exactly which columns to apply; everything else on the case (received
# amount, paid status, dispositions, notes, visits, calls, history) is left untouched. If a
# caller / FOS / team-lead column is corrected, the case is RE-ASSIGNED to the new person.
# This is NOT the DPR tool (DPR marks paid/unpaid through the payment pipeline) — this only fixes the
# source case data.

# field -> (label, is_reassignment). Payment/action/feedback fields are deliberately NOT correctable
# here so progress can never be clobbered. account_no / bank / product are the match key, not editable.
_CORRECTABLE = {
    "customer_name": ("Customer name", False),
    "phone": ("Phone", False),
    "alt_phone": ("Alt phone", False),
    "address": ("Address 1", False),
    "address2": ("Address 2", False),
    "address3": ("Address 3", False),
    "pincode": ("Pincode 1", False),
    "pincode2": ("Pincode 2", False),
    "pincode3": ("Pincode 3", False),
    "card_no": ("Card no", False),
    "segment": ("Segment", False),
    "branch": ("Branch / location", False),
    "team": ("Area", False),
    "cat": ("Category", False),
    "bucket": ("Bucket", False),
    "cycle": ("Cycle", False),
    "enr": ("ENR", False),
    "norm_amount": ("OD NORM", False),
    "stab_amount": ("OD STAB", False),
    "total_outstanding": ("TOS", False),
    "principal_outstanding": ("POS", False),
    "min_amount_due": ("MAD", False),
    "funding_amount": ("Funding amount", False),
    "rollback_amount": ("Rollback target", False),
    "vehicle_type": ("Vehicle type", False),
    "brand": ("Brand", False),
    "vehicle_num": ("Vehicle no", False),
    "old_new": ("Old / New", False),
    "caller_name": ("Telecaller (TC)", True),
    "fos_name": ("Field officer (FOS)", True),
    "team_lead": ("Team lead (TL)", True),
}
# Use the upload parser's own extra-field mappings, rather than a second heading dictionary.
# Scheduling/contact feedback is owned by the corresponding workflows, not source corrections.
_CORRECT_PROTECTED_EXTRA = {"x_ptp_date", "x_paid_date", "x_mode_of_payment", "x_due_date",
                            "x_traced_contact", "x_traced_address"}
_CORRECT_EXTRA = {"x_" + v[2:] for v in HEADER_MAP.values() if v.startswith("x:")} - _CORRECT_PROTECTED_EXTRA
_CORRECTABLE.update({f: (f[2:].replace("_", " ").title(), False) for f in sorted(_CORRECT_EXTRA)})
_CORRECT_MONEY = {"enr", "norm_amount", "stab_amount", "total_outstanding",
                  "principal_outstanding", "min_amount_due", "funding_amount", "rollback_amount"}


def _correct_headers(metadata):
    """Explain every source heading using exactly the same map as the upload parser."""
    out = []
    for h in metadata.get("headers", []):
        raw = h["mapped_field"]
        field = {"_caller": "caller_name", "_fos": "fos_name", "_area": "team"}.get(raw, raw)
        if field and field.startswith("x:"):
            field = "x_" + field[2:]
        if field in _CORRECTABLE:
            use = "correctable"
        elif field in ("account_no", "bank", "product"):
            use = "matching"
        elif field == "_emi_os":
            use = "derived"
        elif field == "_ignore":
            use = "ignored"
        elif field:
            use = "protected"
        else:
            use = "unrecognised"
        out.append({**h, "field": field, "use": use,
                    "label": _CORRECTABLE.get(field, (field or "Not recognised", False))[0]})
    return out


def _correct_norm(v):
    return (str(v).strip() or None) if v not in (None, "") else None


def _correct_user_maps(db: Session):
    """code(UPPER) -> user maps for resolving a corrected TC / FOS / TL cell to a person."""
    caller_by, fos_by, tl_by, tl_by_name = {}, {}, {}, {}
    for u in db.query(models.User).filter(models.User.is_active.is_(True)).all():
        code = (u.emp_code or "").strip().upper()
        role = (u.role or "").lower()
        if code:
            if role in ("telecaller", "caller"):
                caller_by[code] = u
            if role == "fos":
                fos_by[code] = u
            if role == "teamlead":
                tl_by[code] = u
        if getattr(u, "also_caller", False) and getattr(u, "tc_emp_code", None):
            caller_by[u.tc_emp_code.strip().upper()] = u
        if getattr(u, "also_field_agent", False) and getattr(u, "fos_emp_code", None):
            fos_by[u.fos_emp_code.strip().upper()] = u
        tlc = (getattr(u, "tl_emp_code", None) or "").strip().upper()
        if tlc and (role == "teamlead" or getattr(u, "also_team_lead", False)):
            tl_by[tlc] = u
        if (role == "teamlead" or getattr(u, "also_team_lead", False)) and u.name:
            name = u.name.strip().upper()
            tl_by_name[name] = None if name in tl_by_name else u
    return caller_by, fos_by, tl_by, tl_by_name


def _money_eq(a, b):
    try:
        from decimal import Decimal as _D
        return _D(str(a or 0)) == _D(str(b or 0))
    except Exception:
        return str(a) == str(b)


def _correct_scan(records, default_bank, product, db, want_fields=None, scope=None, diagnostics=None):
    """Match each file row to existing case(s) and compute, per correctable field, which cases would
    change. Returns (per_field, matched_accounts, unmatched, apply_plan). apply_plan is a list of
    (case, {field: newvalue}, {reassign dicts}) ready to write when want_fields is given."""
    caller_by, fos_by, tl_by, tl_by_name = _correct_user_maps(db)
    per_field = {}            # field -> {"label","reassign","changes":int,"samples":[...]}
    for f, (label, isre) in _CORRECTABLE.items():
        per_field[f] = {"field": f, "label": label, "reassign": isre, "changes": 0, "samples": []}
    matched_accounts = set()
    unmatched = 0
    plan = []
    stats = diagnostics if diagnostics is not None else {}
    stats.update(rows_missing_identifier=0, rows_ambiguous=0, matched_by_account=0, matched_by_card=0)
    stats["unresolved_assignments"] = 0

    def resolve_person(field, raw):
        code = _correct_norm(raw)
        if not code:
            return None, None, "blank"
        key = str(code).strip().upper()
        if field == "caller_name":
            u = caller_by.get(key)
        elif field == "fos_name":
            u = fos_by.get(key)
        else:
            u = tl_by.get(key) or tl_by_name.get(key)
        return (u, key, "" if u else "unknown")

    for rec in records:
        k = record_to_case_kwargs(rec)
        k.update({f: v for f, v in (k.get("extra") or {}).items() if f in _CORRECT_EXTRA})
        acct = _correct_norm(k.get("account_no"))
        card = _correct_norm(k.get("card_no"))
        if not acct and not card:
            stats["rows_missing_identifier"] += 1
            unmatched += 1
            continue
        q = db.query(models.Case).filter(models.Case.removed.isnot(True))
        sc = scope or {}
        if sc.get("selected"):
            # Empty values in a chosen portfolio mean an empty dimension, not 'all portfolios'.
            from sqlalchemy import func as _f
            for dimension in ("bank", "product", "period"):
                q = q.filter(_f.coalesce(getattr(models.Case, dimension), "") == (sc.get(dimension) or ""))
            q = q.filter(_f.lower(_f.trim(_f.coalesce(models.Case.branch, ""))) == (sc.get("branch") or "").strip().lower())
        # A chosen portfolio scope wins over the file's own bank/product columns.
        bank = None if sc.get("selected") else (_correct_norm(sc.get("bank")) or _correct_norm(k.get("bank")) or _correct_norm(default_bank))
        prod = None if sc.get("selected") else (_correct_norm(sc.get("product")) or _correct_norm(k.get("product")) or _correct_norm(product))
        if bank:
            q = q.filter(models.Case.bank == bank)
        if prod:
            q = q.filter(models.Case.product == prod)
        if _correct_norm(sc.get("period")):
            q = q.filter(models.Case.period == _correct_norm(sc.get("period")))
        if _correct_norm(sc.get("branch")):
            from sqlalchemy import func as _f
            q = q.filter(_f.lower(_f.trim(models.Case.branch)) == _correct_norm(sc.get("branch")).lower())
        # Prefer the account number. Fall back to a card ONLY when the file has no account;
        # never silently use a different card's case to repair a mistyped account number.
        column = models.Case.account_no if acct else models.Case.card_no
        cases = q.filter(column == (acct or card)).limit(2).all()
        if not cases:
            unmatched += 1
            continue
        if len(cases) > 1:
            stats["rows_ambiguous"] += 1
            unmatched += 1
            continue
        stats["matched_by_account" if acct else "matched_by_card"] += 1
        matched_accounts.add(cases[0].id)
        for cs in cases:
            row_sets = {}       # field -> new value to set on the case
            row_reassign = {}   # field -> user to assign
            for field, (label, isre) in _CORRECTABLE.items():
                if field not in k:
                    continue
                newraw = k.get(field)
                if isre:
                    u, code, why = resolve_person(field, newraw)
                    if why:                               # blank or unknown code → skip (don't unassign)
                        if why != "blank":
                            stats["unresolved_assignments"] += 1
                        continue
                    cur_id = (cs.assigned_caller_id if field == "caller_name"
                              else cs.assigned_fos_id if field == "fos_name" else None)
                    if field == "team_lead":
                        changed = _correct_norm(cs.team_lead) != _correct_norm(u.name)
                    else:
                        changed = cur_id != u.id
                    if not changed:
                        continue
                    old_disp = (cs.caller_name if field == "caller_name"
                                else cs.fos_name if field == "fos_name" else cs.team_lead) or "—"
                    new_disp = f"{u.name} ({u.emp_code})"
                    row_reassign[field] = u
                else:
                    newv = _correct_norm(newraw)
                    if newv is None:
                        continue
                    curv = (cs.extra or {}).get(field) if field in _CORRECT_EXTRA else getattr(cs, field, None)
                    if field in _CORRECT_MONEY:
                        if _money_eq(curv, newraw):
                            continue
                        old_disp, new_disp = str(curv), str(newraw)
                    else:
                        if _correct_norm(curv) == newv:
                            continue
                        old_disp, new_disp = (curv or "—"), newv
                    row_sets[field] = newraw if field in _CORRECT_MONEY else newv
                # record the change in preview stats
                pf = per_field[field]
                pf["changes"] += 1
                if len(pf["samples"]) < 5:
                    pf["samples"].append({"account": acct or card, "customer": cs.customer_name,
                                          "old": str(old_disp)[:60], "new": str(new_disp)[:60]})
            if want_fields and (row_sets or row_reassign):
                plan.append((cs, {f: v for f, v in row_sets.items() if f in want_fields},
                             {f: u for f, u in row_reassign.items() if f in want_fields}))
    return per_field, matched_accounts, unmatched, plan


@router.post("/correct/preview")
async def correct_preview(file: UploadFile = File(...), default_bank: str | None = Form(None),
                          product: str | None = Form(None),
                          scope_selected: bool = Form(False),
                          scope_bank: str | None = Form(None), scope_product: str | None = Form(None),
                          scope_branch: str | None = Form(None), scope_period: str | None = Form(None),
                          actor: models.User = Depends(require_roles("admin", "headoffice")),
                          db: Session = Depends(get_db)):
    """Re-read a corrected ORIGINAL portfolio file and show which case COLUMNS would change (with
    before→after samples + a count per column), so the admin/HO can tick exactly which to apply.
    Scoped to the chosen portfolio (period/bank/product/branch). Nothing is written."""
    content = await file.read()
    metadata = {}
    try:
        records, sheet = import_workbook(content, default_bank=default_bank, metadata=metadata)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    scope = {"bank": scope_bank, "product": scope_product, "branch": scope_branch, "period": scope_period,
             "selected": scope_selected}
    diagnostics = {}
    per_field, matched, unmatched, _ = _correct_scan(records, default_bank, product, db, scope=scope,
                                                   diagnostics=diagnostics)
    cols = [v for v in per_field.values() if v["changes"] > 0]
    detected = _correct_headers(metadata)
    for column in cols:
        column["source_headings"] = list(dict.fromkeys(
            h["heading"] for h in detected if h["field"] == column["field"]
        ))
    cols.sort(key=lambda x: (-x["changes"], x["label"]))
    return {"file": file.filename, "sheet": sheet, "rows_in_file": len(records),
            "accounts_matched": len(matched), "rows_no_match": unmatched, "columns": cols,
            "detected_columns": detected, **diagnostics}


@router.post("/correct/apply")
async def correct_apply(file: UploadFile = File(...), default_bank: str | None = Form(None),
                        product: str | None = Form(None), fields: str = Form(""),
                        scope_selected: bool = Form(False),
                        scope_bank: str | None = Form(None), scope_product: str | None = Form(None),
                        scope_branch: str | None = Form(None), scope_period: str | None = Form(None),
                        actor: models.User = Depends(require_roles("admin", "headoffice")),
                        db: Session = Depends(get_db)):
    """Apply ONLY the selected columns from the corrected file onto the matched cases, confined to the
    chosen portfolio (period/bank/product/branch). Reassigns the case when a TC / FOS / TL column is
    selected and changed. Leaves received amount, paid status, dispositions, notes, visits, calls and
    history exactly as they are."""
    want = {f.strip() for f in (fields or "").split(",") if f.strip() and f.strip() in _CORRECTABLE}
    if not want:
        raise HTTPException(status_code=400, detail="Select at least one valid column to update.")
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    scope = {"bank": scope_bank, "product": scope_product, "branch": scope_branch, "period": scope_period,
             "selected": scope_selected}
    diagnostics = {}
    _pf, matched, unmatched, plan = _correct_scan(records, default_bank, product, db, want_fields=want,
                                                scope=scope, diagnostics=diagnostics)

    cases_changed = 0
    field_changes = {f: 0 for f in want}
    reassigned = {"caller_name": 0, "fos_name": 0, "team_lead": 0}
    for cs, sets, reassign in plan:
        if not sets and not reassign:
            continue
        touched = False
        addr_changed = False
        for f, v in sets.items():
            if f in _CORRECT_EXTRA:
                cs.extra = {**(cs.extra or {}), f: v}
            else:
                setattr(cs, f, v)
            field_changes[f] = field_changes.get(f, 0) + 1
            touched = True
            if f in ("address", "pincode"):
                addr_changed = True
            if f in ("address2", "pincode2"):
                cs.latitude2 = cs.longitude2 = cs.geo_precision2 = None
                cs.geo_attempted_at = None
            if f in ("address3", "pincode3"):
                cs.latitude3 = cs.longitude3 = cs.geo_precision3 = None
                cs.geo_attempted_at = None
        if addr_changed and cs.location_source != "field":
            cs.latitude = cs.longitude = None
            cs.location_source = None
            cs.geo_attempted_at = None
        for f, u in reassign.items():
            if f == "caller_name":
                cs.assigned_caller_id = u.id
                cs.caller_name = u.name
            elif f == "fos_name":
                cs.assigned_fos_id = u.id
                cs.fos_name = u.name
                if u.branch and not cs.branch:
                    cs.branch = u.branch
            elif f == "team_lead":
                cs.team_lead = u.name
            reassigned[f] = reassigned.get(f, 0) + 1
            field_changes[f] = field_changes.get(f, 0) + 1
            touched = True
        if touched:
            cases_changed += 1

    if cases_changed:
        audit.record(db, actor, "correct_columns", entity_type="import",
                     detail=f"{file.filename}: {cases_changed} cases, columns={sorted(want)} (sheets: {sheet})")
        db.commit()
    else:
        db.rollback()
    return {"committed": bool(cases_changed), "file": file.filename, "sheet": sheet,
            "cases_changed": cases_changed, "rows_no_match": unmatched,
            "field_changes": field_changes, "reassigned": reassigned, **diagnostics}


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
                               segment=(segment or None), period=period, branch=(branch or None),
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
            _old_addr2 = (existing.address2, existing.pincode2)
            _old_addr3 = (existing.address3, existing.pincode3)
            # update amounts / status, don't duplicate
            for k in ("funding_amount", "received_amount", "pending_amount", "paid_status",
                      "disposition", "remarks", "address", "address2", "address3",
                      "pincode", "pincode2", "pincode3", "phone",
                      "enr", "norm_amount", "stab_amount", "rollback_amount", "norm_stab",
                      "total_outstanding", "principal_outstanding",
                      "caller_name", "fos_name", "team", "bucket", "cycle", "final_status"):
                if kwargs.get(k) is not None:
                    setattr(existing, k, kwargs[k])
            # If the re-upload changed the primary address/pincode, this case needs geocoding
            # again — clear the "attempted" marker (and the geocoded pin, unless a FOS verified it
            # in the field) so the next Geocode run picks up the NEW address.
            if (existing.address, existing.pincode) != _old_addr:
                existing.geo_attempted_at = None
                if existing.location_source != "field":
                    existing.latitude = existing.longitude = None
                    existing.location_source = None
            # Same for the 2nd / 3rd address lines — a changed line clears its own pin + re-arms
            # geocoding so the next run fills latitude{2,3}/longitude{2,3}.
            if (existing.address2, existing.pincode2) != _old_addr2:
                existing.latitude2 = existing.longitude2 = existing.geo_precision2 = None
                existing.geo_attempted_at = None
            if (existing.address3, existing.pincode3) != _old_addr3:
                existing.latitude3 = existing.longitude3 = existing.geo_precision3 = None
                existing.geo_attempted_at = None
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
def recent_batches(limit: int = 25, offset: int = 0, q: str | None = None,
                   db: Session = Depends(get_db),
                   admin: models.User = Depends(require_roles("admin", "headoffice"))):
    """Portfolio uploads, newest first — so admin/head office can undo a wrong upload, however old.
    Paginated (limit/offset) with an optional text filter `q` (matches filename, bank or product),
    so older batches stay findable. live = cases still active; removed = already pulled out.
    Returns {items, total, offset, limit} so the UI can show a Next-page button."""
    from sqlalchemy import func, or_
    limit = max(1, min(limit, 200))
    base = db.query(models.ImportBatch)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.filter(or_(models.ImportBatch.filename.ilike(like),
                               models.ImportBatch.bank.ilike(like),
                               models.ImportBatch.product.ilike(like),
                               models.ImportBatch.segment.ilike(like),
                               models.ImportBatch.branch.ilike(like),
                               models.ImportBatch.period.ilike(like)))
    total = base.count()
    rows = (base.order_by(models.ImportBatch.created_at.desc())
            .offset(max(0, offset)).limit(limit).all())
    names = {u.id: u.name for u in db.query(models.User).all()}
    # counts per batch (live vs removed) only for the batches on THIS page
    ids = [b.id for b in rows] or [-1]
    live = dict(db.query(models.Case.import_batch_id, func.count(models.Case.id))
                .filter(models.Case.import_batch_id.in_(ids), models.Case.removed.isnot(True))
                .group_by(models.Case.import_batch_id).all())
    gone = dict(db.query(models.Case.import_batch_id, func.count(models.Case.id))
                .filter(models.Case.import_batch_id.in_(ids), models.Case.removed.is_(True))
                .group_by(models.Case.import_batch_id).all())
    items = [{
        "id": b.id, "filename": b.filename, "bank": b.bank, "product": b.product,
        "segment": getattr(b, "segment", None), "period": getattr(b, "period", None),
        "branch": getattr(b, "branch", None),
        "rows_total": b.rows_total, "rows_imported": b.rows_imported,
        "uploaded_by": names.get(b.uploaded_by) or "—",
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "live": int(live.get(b.id, 0)), "removed": int(gone.get(b.id, 0)),
    } for b in rows]
    return {"items": items, "total": total, "offset": max(0, offset), "limit": limit}


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
