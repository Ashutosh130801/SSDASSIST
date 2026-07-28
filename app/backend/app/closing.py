"""Per-product case-closing rules.

Each product closes (drops out of the FOS/caller/live views and becomes admin-only
history) on a date decided by its closing pattern:

  - "cyc"       : cycle-wise. The sheet's CYC/CYCLE column is the day of the month
                  (CYC 1 = the 1st, CYC 5 = the 5th, ...). The case closes AFTER that
                  day of its period month.
  - "month_end" : closes after the last day of its period month.
  - "due_date"  : closes after the due date read from the upload sheet. Used for BRBL.

Source of truth: SSD PRODUCTS.xlsx (PORTFOLIO / PRODUCT / CLOSINGS). Keyed by
(bank, product). Anything not listed defaults to month-end (the safe majority case).
Any product whose name contains "BRBL" is forced to due-date, per the RBL/BRBL rule.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

# Normalise a bank/product label for matching: uppercase, strip all non-alphanumerics.
def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


# (bank, product) -> "cyc" | "month_end".  BRBL handled separately as "due_date".
_RULES_RAW = {
    "ICICI": {
        "DR": "cyc", "FR": "cyc", "FCPU": "cyc", "2 BKT": "cyc", "4BKT": "cyc",
        "3 BKT": "cyc", "SFFRC": "month_end", "180+": "month_end",
    },
    "AXIS": {
        "X BKT": "cyc", "2 BKT": "cyc", "3 BKT": "cyc",
        "BL X BKT": "month_end", "PL X BKT": "month_end", "PL NPA": "month_end",
        "180+": "month_end", "CC NPA": "month_end",
    },
    "RBL": {"BRBL BKT 3": "due_date"},
    "PIRAMAL": {"2 BKT": "month_end"},
    "NAVI": {"X-5BKT": "month_end", "180+": "month_end"},
    "CHOLA": {"CD 2,3,4": "month_end"},
    "HERO FIN CORP": {"NPA": "month_end", "180+": "month_end"},
    "HOMECREDIT": {"180+": "month_end"},
    "TVS CREDIT": {"180+": "month_end"},
}

# Build a fast lookup keyed by (norm(bank), norm(product)).
_RULES = {}
for _bank, _prods in _RULES_RAW.items():
    for _prod, _rule in _prods.items():
        _RULES[(_norm(_bank), _norm(_prod))] = _rule

DEFAULT_RULE = "month_end"


def closing_type(bank: str | None, product: str | None) -> str:
    """The closing pattern for a product: 'cyc' | 'month_end' | 'due_date'."""
    if product and "BRBL" in str(product).upper():
        return "due_date"
    return _RULES.get((_norm(bank), _norm(product)), DEFAULT_RULE)


def parse_cycle_day(cyc) -> int | None:
    """CYC 5 / cyc5 / '5' / 5  -> 5.  Returns None if no number is present."""
    if cyc is None:
        return None
    m = re.search(r"(\d{1,2})", str(cyc))
    if not m:
        return None
    d = int(m.group(1))
    return d if 1 <= d <= 31 else None


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def month_end_date(period: str) -> date | None:
    """period 'YYYY-MM' -> last calendar day of that month."""
    try:
        y, m = int(period[:4]), int(period[5:7])
        return date(y, m, _last_day(y, m))
    except (ValueError, TypeError, IndexError):
        return None


def compute_close(bank: str | None, product: str | None, period: str | None,
                  cyc=None, due_date: date | None = None,
                  force_type: str | None = None) -> tuple[date | None, str]:
    """Return (close_date, closing_type) for a case.

    close_date is the LAST day the case stays visible to field/calling staff; the day
    after, it moves to admin-only monthly history. None means 'no computed close'
    (kept visible until an admin acts). `force_type` overrides the rule (used by the
    admin-defined closing rule for a custom product)."""
    ctype = force_type or closing_type(bank, product)

    if ctype == "due_date":
        if due_date:
            return due_date, "due_date"
        # No due date on the sheet -> fall back to month-end so it still closes.
        return month_end_date(period), "month_end"

    if ctype == "cyc":
        day = parse_cycle_day(cyc)
        if day and period:
            try:
                y, m = int(period[:4]), int(period[5:7])
                return date(y, m, min(day, _last_day(y, m))), "cyc"
            except (ValueError, TypeError):
                pass
        # cyc product but no usable cycle number -> fall back to month-end.
        return month_end_date(period), "month_end"

    return month_end_date(period), "month_end"
