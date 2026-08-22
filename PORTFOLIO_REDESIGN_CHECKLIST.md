# Portfolio Redesign + Universal Filters — Build Checklist

Goal: bank-first portfolio navigation, no accidental branch-splitting, rich multi-select
filters everywhere, clickable FOS/caller names, and analytics that re-sync to the active filter.

## Ground rules
- Do NOT override FOS branch inheritance. A case still inherits its FOS's home branch.
- Branch-splitting a portfolio happens ONLY when a branch/location was EXPLICITLY chosen at
  upload time. Everything else stays merged as one bank→product portfolio.
- Clickable person names (open individual performance) everywhere EXCEPT the Manpower screen.
- Filters are multi-select and AND-combined (e.g. PAID + Cycle 2 + FOS X). Charts/percentages
  must recompute for the active filter.

---
## Phase 1 — Backend: branch model + import (Task #194) ✅ DONE
- [x] Add `branch_explicit` boolean column to Case (+ auto-migration in `_ensure_columns`).
- [x] Import: keep FOS-branch inheritance; set `branch_explicit=True` ONLY when the upload
      passed an explicit branch (new + existing-case branches).
- [x] Existing rows default False (NULL) → they stay merged. No destructive backfill needed.

## Phase 2 — Backend: bank-first endpoints (Task #195) ✅ DONE
- [x] `GET /cases/portfolio-banks` → [{bank, logo_domain, product_count, count, received, pending}]
- [x] `product-summary` reshaped: group by BANK+PRODUCT, adds `branch_split` + `branches[]`.
- [x] `branch_split` = product has ≥1 case with branch_explicit=True.
- [x] `_bank_domain` map (ICICI→icicibank.com, …) for Clearbit logos; unknown → null (initials).

## Phase 3 — Backend: case-list filters (Task #196) ✅ DONE
- [x] `list_cases` params: `cycles` (csv), `fos_ids` (csv), `caller_ids` (csv), + `paid_status`,
      `branch` already present — all AND-combined.
- [x] `GET /cases/filter-options?bank&product&branch` → {cycles[], fos[{id,name,code}], callers[]}

## Phase 4 — Backend: MIS + performance filters (Task #197) ✅ DONE
- [x] `compute_mis` / `/api/mis` + `/mis/download` accept cycles[], fos_ids[], caller_ids[], paid.
- [x] `my-performance` accepts bank, product, cycles[]; recomputes cards + leaderboard.
- [x] `GET /mis/performance?emp_id&role` = view ANY FOS/caller's performance (for clickable names).
- [x] All pcts/leaderboard/pivots recompute against the filtered case set.
- [x] py_compile clean on all backend files.

## Phase 5 — Web (Tasks #198, #199) ✅ DONE
- [x] Product view = bank cards (Clearbit logo `logo.clearbit.com/<domain>` + initials fallback).
- [x] Bank → products → (branch cards only if branch_split) → case list.
- [x] Case list adds Cycle / FOS / Caller columns; FOS + Caller are PersonLinks.
- [x] Filter bar: multi cycle, multi FOS, multi caller, paid + existing; AND-combined.
- [x] `<PersonLink>` opens individual performance (PerfModal + PerfHost via window.__ssdOpenPerf);
      wired on case list + MIS FOS/caller tables + both leaderboards. Not on Manpower.
- [x] MIS view: cycle/FOS/caller multi-filters; tables + charts + % re-sync (all read `d`).
- [x] My-Performance card: bank / product / cycle filters; dashboard re-syncs.
- [x] Backend group rows + leaderboards now carry `emp_id` for clickable names.
- [x] Bump `app.jsx?v=149` in index.html. Transpile + py_compile clean.

## Phase 6 — Native (Task #200) ✅ DONE
- [x] New models: PortfolioBank, ProductSummary (+branches), FilterOptions, Performance.
- [x] ApiService: portfolio-banks, product-summary, filter-options, /mis/performance;
      cases() extended with product/branch/cycles/fos_ids/caller_ids.
- [x] Repository: portfolioBanks/productSummary/filterOptions/performance/portfolioCases.
- [x] New `PortfolioScreen.kt`: banks (Clearbit logo via SubcomposeAsyncImage + initials
      fallback) → products → location cards (only when branch_split) → filtered case list.
- [x] Case list filter bar: Paid + multi Cycle / FOS / Caller chips (AND-combined).
- [x] `CaseCard` FOS/caller become tappable PersonChips → PerformanceDialog
      (KPIs + FTD/MTD/LMTD/Overall TrendStrip + per-portfolio rows).
- [x] Wired PortfolioScreen as "Accounts" for admin / head office / manager / team lead.

## Phase 7 — Verify (Task #201) ✅ DONE
- [x] `python3 -m py_compile` backend — OK.
- [x] Babel transpile app.jsx — OK; `app.jsx?v=149`.
- [x] Kotlin brace/paren balance on all changed files — OK. (Full Kotlin compile runs in CI on push.)

## Ship steps (user, from Windows)
1. Restart backend (`run_local.bat` in app/backend) — picks up branch_explicit column, new
   endpoints, and the pending backfill.
2. `git add/commit/push` → CI rebuilds the APK (auto-stamps version) + serves the new web bundle.
3. Re-upload / re-verify: a file with NO branch chosen = one merged portfolio; a file WITH a
   branch = split into location cards.

## Notes / decisions
- Bank logos: Clearbit live service, name→domain map maintained in frontend, initials fallback onerror.
- Scope: web + native together.
