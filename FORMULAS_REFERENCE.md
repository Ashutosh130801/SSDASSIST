# RecoverIQ — Formula, Notation & Column Reference

A complete map of every calculation the system performs, the terminology it uses, and
which **upload-sheet column → database field** each value comes from. Use the **VERIFY?**
flags to confirm or correct the business rule.

_All money is stored with 2 decimals. All percentages are rounded to 2 decimals. "IST" = Asia/Kolkata._

---

## 1. Terminology / notation

| Term | Meaning | Stored field |
|---|---|---|
| **ENR** | End Net Receivables (the MIS % base) = EMI Outstanding + Current Balance | `enr` |
| **TOS** | Total Outstanding | `total_outstanding` |
| **POS** | Principal Outstanding | `principal_outstanding` |
| **MAD** | Minimum Amount Due | `min_amount_due` |
| **TAD** | Total Amount Due (mapped to TOS) | `total_outstanding` |
| **Funding / Target Amt** | Committed/funded amount (funding sheets only) | `funding_amount` |
| **NORM / STAB / ROLLBACK** | Paid category chosen at payment time (settlement type) | `norm_stab` |
| **OD NORM / OD STAB** | Per-case NORM / STAB target amounts | `norm_amount` / `stab_amount` |
| **CASH COLL / Received** | Cash actually collected so far | `received_amount` |
| **Pending** | Balance still to collect | `pending_amount` |
| **CYC** | Cycle day-of-month the product closes on | `cycle` |
| **DPD / Bucket** | Days-past-due bucket (R30 / X-BKT …) | `bucket` |
| **AREA** | Region/area code (GTR, VSP, …) — the "area-wise" dimension | `team` |
| **TEAM LEAD** | Team lead name/code | `team_lead` |
| **CALLER / FOS** | Assigned caller / field officer (by name in sheet, id at runtime) | `caller_name` / `fos_name`, `assigned_caller_id` / `assigned_fos_id` |
| **CAT** | CAT-ALLO category (J / I / C …) | `cat` |
| **Period** | Working month, `YYYY-MM` | `period` |

---

## 2. Column → field mapping (upload sheet → case)

Headers are matched case/space/symbol-insensitive. Main aliases (not exhaustive):

| Case field | Sheet header aliases |
|---|---|
| `customer_name` | NAME, CUS NAME, CUSTOMER NAME, CUST NAME |
| `phone` | PHONE, MOBILE, MOB NO, CONTACT NO, REG MOBILE |
| `alt_phone` | ALT NO, ALTERNATE MOBILE, SECONDARY MOBILE |
| `account_no` | ACCOUNT NO, ACC NO, ACC.NO |
| `card_no` | CARD NO, CC NO |
| `product` | PRODUCT, CARD TYPE |
| `address` | ADDRESS, ADD 1, RES ADDRESS, COMMUNICATION ADDRESS |
| `pincode` | PINCODE, PIN, ZIP, POSTAL CODE |
| `bucket` | BKT, BUCKET, DPD, ALLOCATION DPD BRACKET |
| `cycle` | CYC, CYCLE |
| `total_outstanding` | TOS, TOTAL OUTS, CURR BAL, **TAD** |
| `principal_outstanding` | POS, PRINCIPAL OUTSTD, PRI |
| `min_amount_due` | MAD |
| `funding_amount` | FUNDING AMOUNT |
| `received_amount` | AMOUNT, RECEIVED AMOUNT, CASH COLL, PAID AMOUNT |
| `pending_amount` | PENDING, PENDING AMOUNT |
| `enr` | ENR (else computed — see §3) |
| `norm_amount` | NORM, OD NORM |
| `stab_amount` | STAB, OD STAB, EMI STAB |
| `rollback_amount` | ROLLBACK, RB, RB AMOUNT |
| `norm_stab` | NORM/STAB, N-STAB, NS (also read from STATUS if blank) |
| `_caller` → resolves to `assigned_caller_id` | CALLER, TC NAME, CALLER ID, TC ID (emp code) |
| `_fos` → resolves to `assigned_fos_id` | FOS, FOS NAME, FOS ID (emp code) |
| `team` (AREA) | AREA, AERA |
| `team_lead` | TEAM, TEAM LEAD, TL, TEAM LEAD ID |
| `cat` | CAT, CAT ALLO, CATEGORY |
| `x:due_date` (closing) | DUE DATE, EMI DUE DATE, PAYMENT DUE DATE |

**Caller/FOS resolution:** the CALLER / FOS column value is matched to a user by **emp-code**
first (e.g. `TC001`, `FO012`), then by exact name, then by a unique partial name.
Team lead column is matched only to **teamlead-role** users (or dual-role team leads by their TL code).

---

## 3. Import-time derived values (excel_io)

- **ENR** (if no ENR column): `enr = EMI_0/S + CURR_BAL`  →  `_emi_os + total_outstanding`.  **VERIFY?**
- **Pending** (if no PENDING column): `pending = STAB − received` when a STAB target exists, **else** `funding − received`.  **VERIFY?**
- **Period**: taken from the upload's month/year selection (`YYYY-MM`).
- **Close date / closing type**: computed per product rule — see §9.

---

## 4. Collection base & pending (the money core)

**Collection base** `_pay_base_total(case)` — the amount a case is "worth":

```
if funding_amount > 0 → base = funding_amount
elif total_outstanding > 0 → base = total_outstanding   (TOS)
else → base = enr
```

So for CC / PL-BL portfolios (no funding amount), **base = TOS** (then ENR).

**Pending** (recomputed on every payment / amount edit / DPR):

```
pending = max( base − received_amount , 0 )
```

Pending is **never negative**, and it stays visible (shows the balance) even after a case is resolved.

**Recovered / Received** = `received_amount` (sum of all cash logged).

---

## 5. Paid / resolved rule

A case becomes **PAID (resolved)** when **either**:

```
a NORM/STAB (settlement) payment is recorded     →  paid_status = PAID, status = paid
OR  pending ≤ 0 (full collection)                →  paid_status = PAID, status = paid
otherwise, if some cash but not settled          →  paid_status = PARTIAL
```

`mark-paid` (DPR / head office) always sets PAID. **VERIFY?** — confirm that any NORM/STAB
amount (even a partial settlement) should count as fully "resolved" while pending still shows the balance.

---

## 6. MIS group aggregation (per FOS / caller / area / team-lead / cat / bucket)

For a group of cases, `%` is **ENR-based**. Definitions:

| Output | Formula | Source |
|---|---|---|
| `count` | number of cases | — |
| `paid` | cases with `paid_status = PAID` | `paid_status` |
| `unpaid` | cases not paid | `paid_status` |
| `enr` | Σ `enr` (all cases in group) | `enr` |
| `paid_enr` | Σ `enr` of **paid** cases | `enr`, `paid_status` |
| `pct` (Paid %) | `paid_enr ÷ enr × 100` | — |
| `norm_pct` | Σ enr(paid & NORM) ÷ total enr × 100 | `enr`, `norm_stab` |
| `stab_pct` | Σ enr(paid & STAB) ÷ total enr × 100 | `enr`, `norm_stab` |
| `rollback_pct` | Σ enr(paid & ROLLBACK) ÷ total enr × 100 | `enr`, `norm_stab` |
| `amount` (Cash / Collected) | Σ `received_amount` | `received_amount` |
| `pending` | Σ `pending_amount` | `pending_amount` |
| `recovery_pct` | **Σ received ÷ Σ enr × 100** | `received_amount`, `enr` |
| `visited` / `not_visited` | count of `visited` flag | `visited` |

> **VERIFY?** `recovery_pct` uses **ENR** as the denominator (cash collected ÷ ENR). If you
> intend "collected ÷ (collected + pending)" or "collected ÷ TOS", tell me and I'll change it.
> Also note NORM% + STAB% + ROLLBACK% = total Paid % (all over the same ENR base).

---

## 7. Employee leaderboard (FOS & caller, vs the ONE product target %)

`product_target` = the single manager-set target % for the whole product (stored under `*ALL*`).

| Output | Formula |
|---|---|
| `target_pct` | product_target (manager-entered) |
| `target_enr` | `enr × target_pct ÷ 100` |
| `achieved_pct` | group `pct` = `paid_enr ÷ enr × 100` |
| `achieved_enr` | `paid_enr` |
| `to_target_pct` | `paid_enr ÷ target_enr × 100` |
| `gap_enr` | `max(target_enr − paid_enr, 0)` |
| `status` | green ≥100% to-target · amber ≥60% · red <60% · none (no target) |
| `cash_coll` | Σ `received_amount` |
| `pending_visit` | count not visited |

---

## 8. Other MIS analytics

**Projection (month-to-date run-rate):**
```
collected_mtd      = Σ payments dated this month (IST)          [CallLog PAYMENT + Visit collected]
projected_month_end = collected_mtd ÷ day_of_month × days_in_month
projected_pct       = projected_month_end ÷ Σ target_enr × 100
achieved_pct        = collected_mtd ÷ Σ target_enr × 100
```

**Funnel:**
```
contacted        = cases with last_contacted_at OR visited
conversion_pct   = paid_of_contacted ÷ contacted × 100
ptp_cases        = disposition in (PTP, RTP)
ptp_kept_pct     = paid PTP cases ÷ ptp_cases × 100
ptp_broken       = PTP, not paid, follow_up_date < today
untouched        = never contacted & never visited
untouched_pending= Σ pending of untouched
```

**Aging** — bucket by days since `last_contacted_at` (IST): Today / ≤7 / ≤30 / >30 / Never; each shows count + Σ pending.

**Obstacles** (per caller): `rate_pct = obstacle-dispositions ÷ total × 100`, where obstacle = DISPUTE, RNR, WRONG NUMBER, SWITCHED OFF, NOT REACHABLE, REFUSED, NC.

**Productivity** (per employee, today): `calls_today`, `visits_today`, `idle` = both 0.

**Field efficiency** (per FOS): `distance_km = Σ visit distance ÷ 1000`; `off_location` = visits whose distance-from-case **> geofence (default 300 m)**; `collected` = Σ visit cash.

**Settlement:**
```
realization_pct        = collected_all ÷ norm_target × 100        (norm_target = Σ norm_amount)
stab_share_pct         = stab_enr ÷ (stab_enr + norm_enr) × 100
leakage                = Σ over STAB-paid cases of max(norm_amount − received, 0)
rollback_realization_pct = rollback_collected ÷ rollback_target × 100
rollback_pct           = rollback_enr ÷ total_enr × 100
```
> **VERIFY?** `leakage` and `realization_pct` use `norm_amount` as the settlement target — confirm.

**Priority list** ordering = `propensity × pending_amount` (unpaid only, top 25).

---

## 9. Case closing (visibility / lock)

Each product closes on a date, after which it's admin-only history:

| Rule | close_date |
|---|---|
| `cyc` | day-of-month from `cycle` column, within the period month |
| `month_end` | last calendar day of the period month |
| `due_date` | the DUE DATE from the sheet (used for BRBL); falls back to month-end if blank |

Default when a product isn't listed = **month_end**. Any product name containing "BRBL" → **due_date**.
A case is "closed/locked" when `close_date < today (IST)`.

**Month buckets:** `current` = `_current_period()` (this IST month); `next` = next month.
Field/calling staff see **current + next** period; the UI now defaults each view to **one** month.

---

## 10. Propensity score (0–100, prioritisation heuristic)

```
start 50
+22 if disposition contains PTP or RTP
+15 if paid_status = PARTIAL
+8  if received_amount > 0
−22 if disposition in (RNR, SWITCH, WRONG, NOT REACHABLE, REFUSED, DISPUTE)
−8  if bucket contains "X"
+5  if last_contacted_at set
−10 if pending_amount > 100000
clamp to [1, 99]
```
_Purely a sort aid; not a financial figure._

---

## 11. DPR bulk update (bank payment report)

- Matches each row to a case by **account/card/loan number** (full value + digits-only).
- **mark_paid**: `amt = sheet amount` (else `base − received`); `received += amt`; `pending = max(base − received, 0)`; sets PAID; NORM/STAB from the sheet.
- Skips rows already PAID (no double counting).
- Full-sync also overwrites any other recognised column present (contact, TOS, bucket, PTP date, …); blank cells never overwrite.

---

## 12. Quick "is it right?" checklist for you

1. **ENR fallback** = EMI O/S + CURR_BAL? (§3)
2. **Pending fallback at import** = STAB − received, else funding − received? (§3)
3. **Base order** funding → TOS → ENR — correct for every portfolio? (§4)
4. **Resolved on any NORM/STAB** even if pending remains? (§5)
5. **recovery_pct denominator** = ENR (vs TOS or collected+pending)? (§6)
6. **Paid % / achieved %** = paid-case ENR ÷ total ENR (an ENR-coverage %, not cash %)? (§6–7)
7. **Settlement realization** = collected ÷ Σ norm_amount? (§8)
8. **Closing rules** per product in the table — all correct? (§9)

Mark any line and I'll change the formula/mapping.
