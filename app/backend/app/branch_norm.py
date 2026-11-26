"""One branch = one spelling.

There is no Branch table — a branch is the text in `branch` columns (users, cases, …), and every
scope check compares it exactly. Typing "Hyderabad" instead of "HYDERABAD" (or leaving a trailing
space) silently created a separate "branch": the manager on the odd spelling saw 0 cases and only
the few staff typed the same way.

This module fixes that for good:
  • merge_case_variants(db) — one-time/idempotent startup merge. Every spelling that differs only by
    capitals or surrounding spaces is folded into the DOMINANT spelling of that city (the one with
    the most staff + cases; ties prefer the ALL-CAPS form). Runs on every table with a branch column.
  • canonical(db, name) — maps any incoming value to the existing spelling (case/space-insensitive),
    so nothing can create a new variant again.
  • install(SessionClass) — a before_flush hook that applies canonical() to every new or changed row
    with a `branch` attribute, covering all ORM write paths (staff create/edit, Manpower, imports, DPR,
    profile change requests, integrations, legal …) without touching each of them.
"""
from __future__ import annotations

import logging
import threading

from sqlalchemy import event, func
from sqlalchemy.orm import Session

from . import models

log = logging.getLogger("branch_norm")

# Every model with a `branch` column. Users + Cases decide which spelling wins.
BRANCH_MODELS = [m for m in (
    getattr(models, n, None) for n in
    ("User", "Case", "ImportBatch", "LegalCase", "AuditLog", "SupportTicket", "DialerConnection")
) if m is not None and hasattr(m, "branch")]
_WEIGHTED = (models.User, models.Case)

_lock = threading.Lock()
_cache: dict[str, str] = {}          # group key (see _key) -> canonical spelling


def _key(s) -> str:
    """Group key: ignores capitals + spaces, and folds known synonyms (VIZAG → VISAKHAPATNAM)."""
    t = (s or "").strip()
    return models.BRANCH_SYNONYMS.get(t.upper().replace(" ", ""), t.upper()) if hasattr(models, "BRANCH_SYNONYMS") else t.upper()


def _pick(variants: dict[str, int]) -> str:
    """House rule (same as cases.branch_canon_map): if an ALL-CAPS spelling exists use it; otherwise
    the spelling with the most staff + cases; then alphabetical (stable)."""
    return sorted(variants.items(), key=lambda kv: (0 if kv[0].strip() == kv[0].strip().upper() else 1, -kv[1], kv[0]))[0][0].strip()


def _spellings(db: Session) -> dict[str, dict[str, int]]:
    """key -> {raw spelling: weight} across users + cases (other tables count as weight 0)."""
    groups: dict[str, dict[str, int]] = {}
    for m in BRANCH_MODELS:
        weighted = m in _WEIGHTED
        for raw, n in db.query(m.branch, func.count()).filter(m.branch.isnot(None)).group_by(m.branch).all():
            if not str(raw).strip():
                continue
            g = groups.setdefault(_key(raw), {})
            g[raw] = g.get(raw, 0) + (int(n) if weighted else 0)
    return groups


def merge_case_variants(db: Session) -> list[dict]:
    """Fold every case/space variant into the dominant spelling. Idempotent; returns what moved."""
    report = []
    groups = _spellings(db)
    with _lock:
        _cache.clear()
        for key, variants in groups.items():
            canon = _pick(variants)
            _cache[key] = canon
            for raw in variants:
                if raw == canon:
                    continue
                moved = {}
                for m in BRANCH_MODELS:
                    n = db.query(m).filter(m.branch == raw).update({m.branch: canon}, synchronize_session=False)
                    if n:
                        moved[m.__tablename__] = n
                report.append({"from": raw, "to": canon, "moved": moved})
    if report:
        db.commit()
        for r in report:
            log.warning("[branch] merged %r -> %r %s", r["from"], r["to"], r["moved"])
    return report


def canonical(db: Session | None, name):
    """Existing spelling for `name` (ignoring capitals/spaces); otherwise the trimmed input."""
    if name is None:
        return None
    s = str(name).strip()
    if not s:
        return name
    k = _key(s)
    with _lock:
        hit = _cache.get(k)
    if hit:
        return hit
    if db is not None:
        with db.no_autoflush:
            found: dict[str, int] = {}
            for m in _WEIGHTED:
                for raw, n in (db.query(m.branch, func.count())
                               .filter(func.upper(func.trim(m.branch)) == k).group_by(m.branch).all()):
                    found[raw] = found.get(raw, 0) + int(n)
        if found:
            s = _pick(found)
    with _lock:
        _cache[k] = s
    return s


def _before_flush(session: Session, flush_context, instances):
    for obj in list(session.new) + list(session.dirty):
        if not hasattr(obj, "branch") or type(obj) not in BRANCH_MODELS:
            continue
        val = getattr(obj, "branch", None)
        if val is None:
            continue
        canon = canonical(session, val)
        if canon != val:
            obj.branch = canon


def install(session_cls=Session):
    if not event.contains(session_cls, "before_flush", _before_flush):
        event.listen(session_cls, "before_flush", _before_flush)
