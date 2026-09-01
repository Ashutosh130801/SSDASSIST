# Switching SSD Recovery from SQLite to PostgreSQL (Windows)

Your `.env` already points at PostgreSQL:

```
DATABASE_URL=postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery
```

…but the **launcher scripts overrode it to SQLite**, so the app has actually been running on
`ssd_local.db`. This guide sets up Postgres, moves your current data into it, and switches the
app over. Your SQLite scripts are left untouched, so nothing breaks until you're ready.

Do this **once**, in order.

---

## 1. Install PostgreSQL

1. Download the Windows installer from <https://www.postgresql.org/download/windows/> (EDB installer).
2. Run it. When asked for a **password for the `postgres` superuser**, pick one and remember it.
3. Keep the default **port 5432**. Finish the install (Stack Builder is not needed — skip it).

Verify it's running: open **SQL Shell (psql)** from the Start menu, press Enter through the
prompts, and enter the `postgres` password. You should get a `postgres=#` prompt.

## 2. Create the database and user (must match your `.env`)

In that `psql` shell, paste these lines (they create the exact user/db your `.env` expects):

```sql
CREATE USER ssd WITH PASSWORD 'ssd_password';
CREATE DATABASE ssd_recovery OWNER ssd;
GRANT ALL PRIVILEGES ON DATABASE ssd_recovery TO ssd;
```

> If you prefer a stronger password, change it here **and** in `.env`'s `DATABASE_URL` so they match.

Quick connection test:

```
psql "postgresql://ssd:ssd_password@localhost:5432/ssd_recovery" -c "select 1;"
```

A `?column? = 1` result means it's reachable.

## 3. Move your existing data (SQLite → Postgres)

From `app\backend`, with the virtual environment active:

```
call .venv\Scripts\activate.bat
python migrate_sqlite_to_postgres.py
```

This reads `ssd_local.db` (read-only) and copies every table into Postgres, then resets the id
sequences. It's **safe to re-run** — it clears and re-loads the Postgres tables each time.
It prints a per-table row count so you can confirm everything came across.

*(If you have no data worth keeping and want a clean start, skip this step and just run
`seed_postgres.bat` in step 4 to seed staff/admin fresh.)*

## 4. Run on Postgres from now on

- **Start the server:** `run_postgres.bat` (instead of `run_local.bat`).
- **One-time data seed** (only if you skipped step 3 / want to import staff): `seed_postgres.bat`.

On startup the log now prints which database is live, e.g.:

```
[SSD] Database: PostgreSQL  ->  localhost:5432/ssd_recovery
```

If it ever says `SQLite`, you launched a SQLite script by mistake.

## 5. Back up Postgres (automate it — no database self-backs-up)

Neither Postgres **nor** SQLite backs itself up. Set up an automatic nightly dump once and forget it.

**Run a backup now (test it):**

```
backup_postgres.bat
```

It writes a compressed dump to `app\backend\backups\ssd_YYYYMMDD_HHmmss.dump` and deletes dumps
older than 14 days (change `KEEP_DAYS` in the script). It's safe to run while the app is live.

> If it says `pg_dump is not recognized`, add the Postgres `bin` folder to PATH (or uncomment
> the `set PATH=...` line in the script), e.g. `C:\Program Files\PostgreSQL\16\bin`.

**Make it automatic (Windows Task Scheduler):**

1. Open **Task Scheduler** → **Create Basic Task**.
2. Name: `SSD DB backup`. Trigger: **Daily**, time e.g. **1:00 AM**.
3. Action: **Start a program** → Program/script: browse to `app\backend\backup_postgres.bat`.
4. Finish. (Tick "Run whether user is logged on or not" if this is a server.)

That's a real automatic backup — the thing SQLite never actually did for you either.

**Extra safety:** copy the `backups\` folder to a second drive or a cloud-synced folder
(OneDrive/Google Drive) so a disk failure doesn't take the backups with it.

**Restore, if ever needed:**

```
pg_restore -d "postgresql://ssd:ssd_password@localhost:5432/ssd_recovery" --clean --if-exists ssd_YYYYMMDD_HHmmss.dump
```

---

## Which script uses which database?

| Script | Database | Use |
|---|---|---|
| `run_postgres.bat` | **PostgreSQL** (.env) | **Production server — use this** |
| `seed_postgres.bat` | **PostgreSQL** (.env) | One-time staff/admin import into Postgres |
| `migrate_sqlite_to_postgres.py` | SQLite ➜ Postgres | One-time data move |
| `run_local.bat` | SQLite | Quick offline dev only |
| `go_live.bat` / `seed_test.bat` | SQLite | Old dev/test flows (leave as-is) |

## Why move off SQLite

SQLite allows only one writer at a time and locks the whole file. With many field agents pinging
GPS, callers logging, DPR uploads, and the live spreadsheet all writing at once, SQLite throws
"database is locked" errors and stalls. Postgres handles concurrent writers, larger datasets,
the MIS aggregations, real `NUMERIC`/`JSON` typing, and multiple app workers — which is what a
live collections floor (and the upcoming attendance check-ins) needs.
