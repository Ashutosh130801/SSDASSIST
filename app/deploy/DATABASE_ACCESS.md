# Managing users & viewing records

You have two ways to work with the data: the **built-in admin panel** (recommended for
day-to-day), and **direct database access** (for power users / audits).

---

## A. In the app (no database tools needed)

Sign in as an **admin** (`admin@ssdrecovery.in` — change this password immediately).

### Create users & assign roles
**Admin → Staff → + Add staff.** Set name, email, password, and the **Role**:
- **Admin** — full access, uploads, allocation, reports, everything.
- **Field Officer (FOS)** — sees only cases allocated to them; logs GPS visits.
- **Telecaller** — sees only their call queue; logs calls, PTPs, payments.

For field officers you also set **banks**, **assigned pincodes**, and a **base lat/lng**
(these drive automatic case allocation). Use **Edit** on any row to change a role, reset a
password, change banks/pincodes, or deactivate someone.

### View everything being stored & updated
- **Admin → Records** — a live feed of every field visit, call, and payment (who did it,
  when, amount, GPS/photo links), with quick filters and a jump-to-case button. Top tiles
  show total counts: cases, visits, calls, payments, location pings, uploads.
- **Admin → Cases** — every case; click a row for the full drawer (details + history).
- **Admin → PTP Tracker** — all promises to pay (overdue / today / upcoming).
- **Admin → Live Map / Staff → Route** — location pings and 90-day (3-month) route history.
- **Cases → ⬇ Export Excel** — the entire tracker (with visit results, GPS, notes) as a file.

That covers user management and record viewing without touching the database directly.

---

## B. Direct database access

### B1. Cloud SQL (PostgreSQL) — your production database

**Easiest: Cloud SQL Studio (in the browser).**
Google Cloud Console → **SQL → your instance (`ssd-db`) → Studio** → sign in with the DB
user/password → run SQL against database `ssd_recovery`.

**From your PC with psql:**
```
gcloud sql connect ssd-db --user=ssd --database=ssd_recovery
```
(This temporarily allowlists your IP and opens a psql prompt.)

**With a GUI (DBeaver / pgAdgin / TablePlus) via the Cloud SQL Auth Proxy:**
```
# download the proxy from cloud.google.com/sql/docs/postgres/sql-proxy
cloud-sql-proxy YOUR_PROJECT:REGION:ssd-db
# then connect your GUI to  host=127.0.0.1  port=5432  db=ssd_recovery  user=ssd
```

### B2. SQLite — the local test database
When running locally (`run_local.bat`), the database is the file
**`app\backend\ssd_local.db`**. Open it with the free **DB Browser for SQLite**
(https://sqlitebrowser.org) to browse/edit tables directly.

---

## C. Handy SQL snippets

> Passwords are stored **bcrypt-hashed** — you cannot insert a plain-text password by hand.
> To create a login from SQL, generate a hash first (Python):
> `python -c "from passlib.hash import bcrypt; print(bcrypt.hash('YourPass123'))"`

```sql
-- make someone an admin
UPDATE users SET role='admin' WHERE email='name@ssdrecovery.in';

-- change a field officer's pincodes / banks (JSON columns)
UPDATE users SET assigned_pincodes='["530001","530016"]', banks='["ICICI","AXIS"]'
WHERE email='ravi@ssdrecovery.in';

-- deactivate a user (they can't log in)
UPDATE users SET is_active=false WHERE email='old@ssdrecovery.in';

-- create a user (hash the password first, see note above)
INSERT INTO users (name,email,role,hashed_password,is_active,banks,assigned_pincodes)
VALUES ('New TC','tc2@ssdrecovery.in','telecaller','<bcrypt-hash>',true,'[]','[]');

-- see recent activity
SELECT created_at, disposition, ptp_amount, note FROM call_logs ORDER BY created_at DESC LIMIT 50;
SELECT created_at, paid, amount_collected, disposition FROM visits ORDER BY created_at DESC LIMIT 50;

-- collections summary by bank
SELECT bank, COUNT(*) cases, SUM(received_amount) received, SUM(pending_amount) pending
FROM cases GROUP BY bank;
```

> Prefer the **admin panel** for creating users, so passwords are hashed and roles/allocation
> stay consistent. Use raw SQL mainly for read-only audits or bulk fixes.

---

## D. Tables (what's stored where)

| Table | Holds |
|-------|-------|
| `users` | staff: name, email, bcrypt password, **role**, branch, banks, assigned_pincodes, base lat/lng, active flag |
| `cases` | every loan case: customer, bank, account/card, address, pincode, lat/lng, bucket/cycle, funded/received/pending, status, disposition, **assigned_fos_id / assigned_caller_id**, last_contacted_at, follow_up_date |
| `visits` | field visits: GPS lat/lng, accuracy, photo path, location_correct, person_moved, paid, amount_collected, disposition, note |
| `call_logs` | calls **and** payments (disposition `PAYMENT`): amount, ptp_date, note, caller |
| `location_pings` | FO GPS pings (1/min) for live map + 30-day route history |
| `import_batches` | every Excel upload (file, sheet, rows imported/updated) |

Money columns are `NUMERIC(14,2)` (exact); the app computes received/pending with Python
`Decimal`, so totals are always precise.
