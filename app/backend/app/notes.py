"""Unified per-case notes / remarks / dispositions.

Every call log and every field visit can carry a disposition + a free-text note. This module
merges both into one recent-first history for a case, each entry tagged with who wrote it
(name + role) and when, plus the source (call / visit). Used by the PTP tracker (last 5),
case detail, the live sheet, and the bank-feedback export.
"""
from datetime import datetime, timezone, timedelta

from . import models

IST = timezone(timedelta(hours=5, minutes=30))


def _when(dt) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d-%b %H:%M")


def _people(db, people=None):
    if people is not None:
        return people
    return {u.id: (u.name or "—", u.role or "")
            for u in db.query(models.User.id, models.User.name, models.User.role).all()}


def case_notes_map(db, case_ids, limit=None, people=None):
    """Batch: {case_id: [notes]} for many cases in just two queries (no N+1).
    Each note = {at, when, by, role, source, disposition, text}, newest first."""
    ids = [i for i in set(case_ids or []) if i]
    if not ids:
        return {}
    ppl = _people(db, people)
    out: dict[int, list] = {i: [] for i in ids}

    for v in db.query(models.Visit).filter(models.Visit.case_id.in_(ids)).all():
        txt = (v.note or "").strip()
        disp = (v.disposition or "").strip()
        if not txt and not disp:
            continue
        nm, role = ppl.get(v.officer_id, ("—", ""))
        out[v.case_id].append({"at": v.created_at, "when": _when(v.created_at), "by": nm,
                               "role": role or "fos", "source": "visit",
                               "disposition": disp, "text": txt})

    for cl in db.query(models.CallLog).filter(models.CallLog.case_id.in_(ids)).all():
        txt = (cl.note or "").strip()
        disp = (cl.disposition or "").strip()
        if not txt and not disp:
            continue
        nm, role = ppl.get(cl.caller_id, ("—", ""))
        out[cl.case_id].append({"at": cl.created_at, "when": _when(cl.created_at), "by": nm,
                                "role": role or "telecaller", "source": "call",
                                "disposition": disp, "text": txt})

    def _key(e):
        return e["at"] or datetime.min.replace(tzinfo=timezone.utc)

    for cid in out:
        out[cid].sort(key=_key, reverse=True)
        if limit:
            out[cid] = out[cid][:limit]
        for e in out[cid]:
            e["at"] = e["at"].isoformat() if e["at"] else None
    return out


def case_notes(db, case_id, limit=None, people=None):
    """Recent-first notes for one case."""
    return case_notes_map(db, [case_id], limit=limit, people=people).get(case_id, [])


def one_line(n) -> str:
    """A single note rendered as 'DISPO: text — By Name, 24-Aug 14:05'."""
    head = (n.get("disposition") or "").strip()
    body = (n.get("text") or "").strip()
    label = head + (": " if head and body else "") + body
    label = label.strip() or head or body
    who = n.get("by") or ""
    when = n.get("when") or ""
    tail = ", ".join([p for p in [who, when] if p])
    return f"{label} — {tail}".strip(" —") if tail else label


def join_notes(notes, sep=" // ") -> str:
    """Combine a case's notes into one cell for the live sheet / feedback export."""
    return sep.join(one_line(n) for n in (notes or []))
