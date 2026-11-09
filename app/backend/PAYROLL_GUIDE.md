# Salary & Payslips — how it works

Menu: **💰 Salary & Payslips** (Admin, HR) · **🧾 My Payslips** (every employee, once released).
The whole section is behind the salary lock (`SECTION_LOCKED` in `routers/payouts.py` + `SALARY_LOCKED` in `app.jsx`).

## One-time setup (Admin)
1. **Rules & settings** — company details/logo, salary cycle (e.g. 21st→20th), pay-day basis (calendar / 30 / 26 / working days),
   LOP rules (absences from Attendance, late-mark penalty, unpaid-leave words), salary components (Basic %, HRA % of Basic,
   fixed allowances, balance), PF / ESI / Professional Tax slabs / LWF, adjustment types, net-change warning, payslip look.
2. **Bank file formats** — upload your bank's blank bulk-salary file; check the column mapping; set your debit account,
   same-bank IFSC prefix (UTIB for Axis) and mode codes. Works for any bank (xlsx / csv / txt).
3. **Employee salaries** — set each person's monthly gross (or bulk upload the template). Every change is a dated
   revision; history is kept. Per person: PF/ESI/PT/LWF on/off, TDS per month, no-LOP, exempt, cash/cheque, UAN/ESIC.

## Every month
1. **Payroll runs → Start payroll** for the month. It pulls attendance, approved leave, salaries and advances.
2. Review: ⛔ problems (missing bank details, zero pay) must be fixed or the person excluded/held (with a reason);
   ⚠️ warnings (big change vs last month, bank details changed). Override paid days if needed.
3. Add incentives / bonus / arrears / deductions (one by one or Excel upload). Recalculate after any salary change.
4. **Approve** (Admin): password + 2FA + type the net total. Everything locks; advances are recovered.
5. **Bank upload file** → upload it in your bank portal. Or **Send to payout gateway** (RazorpayX, its own approval).
6. Upload the bank's status report (UTR + paid/failed) or **Mark as paid**.
7. **Release payslips** → employees see them under My Payslips; optional **Email payslips** (needs SMTP in .env).

Downloads: salary register (Excel), all payslips (PDF), PF / ESI / PT statement, PF ECR text file.
Reopen (Admin, password + reason) puts an approved, unpaid run back to Draft and restores advance balances.
Every action is in the Audit Log.

Tests: `python -B tests/test_payroll.py`

## Income tax (TDS)
- **Rules & settings → Income tax**: auto/manual mode, default regime, new & old regime slabs, standard deduction,
  87A rebate, cess. Defaults = FY 2025-26 / 2026-27 slabs — update after each Budget.
- Each payroll works out TDS = (projected annual tax − TDS already deducted) ÷ months left. Projection = approved
  months + this month + remaining months at the current salary. Months of the year before RecoverIQ payroll started
  are assumed paid at the current salary — enter any TDS already deducted for them in the employee's declaration
  ("TDS already deducted this year outside RecoverIQ").
- **Income tax tab**: every employee's regime, projected tax, other-regime comparison, TDS per month; edit
  declarations (80C, 80D, rent/HRA, home loan, previous employer…), lock after proof check; download annual tax
  statements (Form 16 Part B layout) and the 24Q quarterly TDS sheet. Employees can set their own regime and
  declarations under My Payslips → My income tax (switch off in settings).
- An employee with a fixed "TDS per month" in their salary keeps that fixed amount.

## Full & final settlement
- **Full & final tab → New**: pick the employee + last working day → Calculate. Suggested lines: last salary (to the
  last working day, with PF/ESI/PT), leave encashment, gratuity (15/26 × basic × years, after 5 years), notice
  shortfall recovery or notice pay, open advance balances. Edit / add / remove any line, save as draft.
- Admin approves (password + 2FA + typed amount): advances close, the employee can be marked as left, and later
  payroll runs never pay them again. Mark paid with date + UTR. Download the settlement letter (PDF).
- Defaults (notice days, encashable leave types, gratuity years/cap) are in Rules & settings → Full & final.

## Android app
- **My Payslips** appears in the menu once the salary section is unlocked: payslip PDFs, this year's tax summary and
  the tax statement.
