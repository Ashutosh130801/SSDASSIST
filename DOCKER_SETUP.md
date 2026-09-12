# RecoverIQ / SSD — Docker Setup (Step by Step)

Docker runs the whole stack — PostgreSQL **and** the API (which also serves the web app) — in two
containers, with your data on persistent volumes. This is the simplest way to run and update the
system on any machine (Windows, Linux, or a cloud VM).

The compose file lives at `app\docker-compose.yml` and already defines:
- **db** — PostgreSQL 16, data kept in the `ssd_pgdata` volume, only reachable from the same PC.
- **api** — builds `app\backend`, serves the web app, uploads kept in the `ssd_uploads` volume,
  auto-creates the admin on startup, and auto-restarts after a reboot/crash.

---

## 1. Install Docker

- **Windows / Mac:** install **Docker Desktop** from https://www.docker.com/products/docker-desktop/
  and launch it (wait until it says "Engine running").
- **Linux (server):** install Docker Engine + the compose plugin:
  ```
  curl -fsSL https://get.docker.com | sh
  ```

Verify:
```
docker --version
docker compose version
```

---

## 2. Get the code

```
git clone https://github.com/Ashutosh130801/SSDASSIST.git
cd SSDASSIST\app
```
(If it's already on the machine, just `cd` into the `app` folder — the one containing
`docker-compose.yml`.)

---

## 3. Create your `.env`

From the `app` folder:
```
copy .env.example .env        REM Windows
cp .env.example .env          # Linux/Mac
```
Open `.env` and set at least:
- `POSTGRES_PASSWORD` — a strong DB password
- `SECRET_KEY` — a long random string (`python -c "import secrets;print(secrets.token_urlsafe(48))"`)
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — your admin login
- Optional keys (LocationIQ, SMTP, TURN, OpenRouter…) — fill only what you use.

This single file drives everything (the compose loads it via `env_file`). `DATABASE_URL` is set
automatically by compose to point at the `db` container — don't add one.

---

## 4. Build and start

From the `app` folder:
```
docker compose up -d --build
```
This builds the API image, starts Postgres, waits until it's healthy, creates the admin, and starts
the server. First build takes a few minutes.

Check it's up:
```
docker compose ps
docker compose logs -f api
```
In the API log you should see:
```
[SSD] Database: PostgreSQL  ->  db:5432/ssd_recovery
Uvicorn running on http://0.0.0.0:8000
```
Open **http://localhost:8000** and log in with your `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
(Ctrl+C just detaches the log view; the containers keep running.)

---

## 5. Seed the staff (employees)

Put your manpower sheet where the container can see it — copy it into `app\backend`, e.g.
`app\backend\SSDE_manpower.xlsx` (that folder is mounted into the container). Then run the seeder
**inside** the api container:
```
docker compose exec api python seed_manpower.py "SSDE_manpower.xlsx"
```
It creates all employees (keeping Emp Codes as-is, dual roles handled), and prints a per-role count.
Staff first-login password is `Ssd@2026`; admin uses your `.env` password.

---

## 6. Import cases and products

Do these through the web app (admin / head-office login): upload products, then each case file
(ICICI FR, AXIS PL&BL, PIRAMAL…) choosing bank/product + month, then DPR uploads. Keeping imports
in the app preserves audit history, allocation and MIS.

---

## 7. Backups (do this once)

The database lives in the `ssd_pgdata` Docker volume. Back it up on a schedule.

Run a backup now (from `app`):
```
docker compose exec -T db pg_dump -U ssd -d ssd_recovery -Fc > ssd_backup_%DATE%.dump
```
(Linux/Mac: `... > ssd_backup_$(date +%F).dump`.)

Automate it: on Windows use **Task Scheduler** to run that command daily; on Linux add a `cron`
line. Copy the dump files to a second drive or cloud folder.

Restore, if ever needed:
```
docker compose exec -T db pg_restore -U ssd -d ssd_recovery --clean --if-exists < ssd_backup_XXXX.dump
```

Also back up the **uploads** volume (visit photos) occasionally:
```
docker run --rm -v ssd_uploads:/data -v %CD%:/backup alpine tar czf /backup/uploads_backup.tgz -C /data .
```

---

## 8. Everyday operations

| Task | Command (run in `app` folder) |
|---|---|
| Start | `docker compose up -d` |
| Stop | `docker compose down` (keeps data volumes) |
| View logs | `docker compose logs -f api` |
| Restart just the API | `docker compose restart api` |
| Update after code changes | `git pull` then `docker compose up -d --build` |
| Open a shell in the API | `docker compose exec api sh` |
| Run the DB reset script | `docker compose exec api python dpr_reset.py --apply` |
| psql into the DB | `docker compose exec db psql -U ssd -d ssd_recovery` |

> `docker compose down -v` also deletes the data volumes — **don't** use `-v` unless you truly want
> to wipe the database and uploads.

---

## 9. Put it on your domain (Cloudflare Tunnel)

The API listens on `localhost:8000`. Point your existing Cloudflare Tunnel's public hostname
(`recoveriq.ssdenterprises.org.in`) at `http://localhost:8000` (see the "Migrate the Cloudflare
Tunnel" section in `SETUP_FROM_SCRATCH.md`). WebSockets (live sheet, chat, presence, voice
signalling) pass through the tunnel automatically. The desktop and Android apps already target the
domain, so they connect once the tunnel is live.

---

## Quick verification checklist
- [ ] `docker compose ps` shows both `db` and `api` as `running`/`healthy`
- [ ] API log says `Database: PostgreSQL`
- [ ] http://localhost:8000 loads and admin can log in
- [ ] `seed_manpower.py` created your staff
- [ ] A test case file imports and shows in the live sheet
- [ ] A `pg_dump` backup file was produced

## Notes
- The `db` port is bound to `127.0.0.1:5432` — only this PC can reach Postgres directly (safe). To
  browse it from a GUI on another machine, use an SSH tunnel, not a compose change.
- Data survives `docker compose down`, reboots, and image rebuilds — it's in named volumes.
- On Windows, run these commands in **PowerShell** or **Command Prompt** with Docker Desktop running.
