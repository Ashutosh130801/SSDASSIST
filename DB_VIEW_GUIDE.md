# Viewing the SSDASSIST database in a GUI

There are two possible databases depending on how you run the app. Steps for both below.

---

## A) SQLite — the simple local mode (`run_local.bat`)

Your entire database is one file: `app\backend\ssd_local.db`.

**Tool: DB Browser for SQLite (free).**

1. Download from https://sqlitebrowser.org → the Windows installer → install it.
2. Open **DB Browser for SQLite** → **Open Database** → select
   `C:\Users\sahoo\Claude\Projects\SSDASSIST\app\backend\ssd_local.db`.
3. **Browse Data** tab → pick a table (`cases`, `users`, `notifications`, `visits`, …) to view
   and edit rows. **Execute SQL** tab → run queries, e.g.:

   ```sql
   SELECT id, customer_name, new_phone, new_address, new_contact_by FROM cases
   WHERE new_phone IS NOT NULL;
   ```

4. If you edit data here, click **Write Changes** to save. Tip: stop the backend (or just
   browse read-only) while editing, so the app and the GUI don't lock the file against
   each other.

---

## B) Postgres — the Docker / self-host mode

The database runs inside the `db` container. I've exposed it to **localhost only** in
`app/docker-compose.yml`, so a GUI on the same PC can connect (it stays off the network).

Apply the change once (on the machine running Docker):

```bash
cd ~/SSDASSIST/app        # or your project's app folder
docker compose -p recoveriq --env-file ~/recoveriq.env up -d
```

**Tool: DBeaver (free) — https://dbeaver.io, or pgAdmin.**

Create a new **PostgreSQL** connection with:

| Field    | Value |
|----------|-------|
| Host     | `localhost` (or `127.0.0.1`) |
| Port     | `5432` |
| Database | `ssd_recovery` |
| Username | `ssd` |
| Password | the `POSTGRES_PASSWORD` from your `recoveriq.env` |

Connect → expand **ssd_recovery → Schemas → public → Tables** to browse, or open an SQL editor.

### No-GUI alternative (works anywhere, nothing to install)
```bash
docker compose -p recoveriq exec db psql -U ssd -d ssd_recovery
# then, at the psql prompt:
\dt                 -- list tables
SELECT COUNT(*) FROM cases;
\q                  -- quit
```

### Browsing the server's Postgres from another computer (safely)
The port is intentionally bound to `127.0.0.1`, so it's not open to the network. To reach it
from your Windows PC, open an SSH tunnel to the Ubuntu server, then point DBeaver at your own
`localhost:5432`:

```powershell
ssh -L 5432:localhost:5432 yourname@<SERVER-IP>
```

Leave that window open and connect DBeaver to `localhost:5432` as in the table above.

> Security note: don't change the binding to `0.0.0.0:5432` on an internet-connected server —
> that would expose the database. The Cloudflare Tunnel only forwards the web app (port 8000),
> never Postgres, so your data stays private.
