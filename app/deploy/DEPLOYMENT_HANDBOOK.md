# RecoverIQ — Deployment Handbook (for non-technical teams)

This is a slow, click-by-click guide to putting the app online on Google Cloud. You do **not**
need to be a programmer. If you can install software, copy-paste text, and follow steps in
order, you can do this. Budget about **1 hour** the first time.

> If at any point something doesn't match what this guide says, **stop and don't guess** — jump
> to section **11. Troubleshooting**, or send the person who gave you this code the exact text
> of the error. It's normal to need one round of help the first time.

---

## 0. What you are actually building (plain English)

You are placing two things inside Google's cloud so they run 24/7:

1. **The app** — one web address (like `https://recoveriq-xxxx.run.app`) that staff open in a
   browser or install on their phone.
2. **The database** — a secure place where all accounts, visits, calls and payments are stored.

Google keeps both running, backed up, and reachable from anywhere. You manage everything else
from **inside the app** as the administrator.

---

## 1. What you need before you start

- [ ] A **Windows PC or a Mac** (any recent one).
- [ ] The **code folder** you were given (it contains a folder named `app`). Save it somewhere
      easy, e.g. `Desktop\RecoverIQ`.
- [ ] A **Google account** (a normal Gmail works).
- [ ] A **credit/debit card** — Google requires one to open a cloud account. Running this app is
      inexpensive for a small team; you can set a budget alert (section 9) and switch it off any
      time (section 10).
- [ ] About **1 hour**, uninterrupted.

> **Honest note:** if nobody on your team is comfortable installing software and copy-pasting
> commands, the easiest path is to appoint **one** slightly tech-comfortable person to do this,
> or hire a freelancer for an hour. It's a one-time setup; after that, everything is done inside
> the app with no technical steps.

---

## 2. Phase 1 — Install the one tool you need (10 min)

You only need **Google Cloud CLI** (a small free program from Google).

1. Open your web browser and go to: `https://cloud.google.com/sdk/docs/install`
2. Download the installer for your system (**Windows** or **macOS**) and run it. Click
   **Next / Continue** through the installer with the default options. Allow it to finish.
3. When it finishes, it may open a window that says "log in" — if so, log in with your Google
   account and click **Allow**.

**Check it worked.** Open a command window:

- **Windows:** press the Start button, type `PowerShell`, open **Windows PowerShell**.
- **Mac:** open **Terminal** (press ⌘-Space, type `Terminal`).

Type this and press Enter:
```
gcloud --version
```
✅ You should see a few lines starting with `Google Cloud SDK`. If you see "not recognized",
close the window, reopen it, and try again. Still failing → Troubleshooting (11).

Now log in (this opens your browser — pick your Google account, click **Allow**):
```
gcloud auth login
```

---

## 3. Phase 2 — Create your cloud project and turn on billing (15 min)

1. In your browser, go to `https://console.cloud.google.com`
2. At the top, click the **project dropdown** (it may say "Select a project") → **New project**.
3. Name it something like `recoveriq` → **Create**. Wait for the notification, then select that
   project from the dropdown so it's the active one.
4. Turn on billing: use the left menu (☰) → **Billing** → **Link a billing account** → follow the
   prompts to add your card. (Google may offer free credits for new accounts.)

> You will **not** be charged for setup. Charges begin only when the app is running, and stay
> small for a modest team. Set a budget alert in section 9 for peace of mind.

**Write down your Project ID.** On the console home page, the **Project ID** is shown near the top
(it looks like `recoveriq` or `recoveriq-431207`). You'll paste it in the next step.

---

## 4. Phase 3 — Get a Google Maps key (10 min, needed for maps)

The live-tracking and route maps need a Google Maps key. (You can skip this and add it later; the
rest of the app works without maps.)

1. In the console, left menu (☰) → **APIs & Services** → **Library**.
2. Search **"Maps JavaScript API"** → click it → **Enable**.
3. Search **"Geocoding API"** → click it → **Enable**.
4. Left menu → **APIs & Services** → **Credentials** → **+ Create credentials** → **API key**.
5. Copy the key that appears (a long string). Keep it safe — you'll paste it next. (We'll lock it
   down in section 9 so it can't be misused.)

---

## 5. Phase 4 — Fill in the settings file (10 min)

Inside your code folder, open: `app` → `deploy` → **`deploy.ps1`** (Windows) or **`deploy.sh`**
(Mac). Open it with **Notepad** (Windows) or **TextEdit** (Mac) — right-click → Open with.

Near the top you'll see a block of lines marked "EDIT THESE". Change only these values, keeping
the quotation marks:

| Line | Change it to |
|------|--------------|
| `PROJECT` | your **Project ID** from step 3 |
| `REGION` | leave as `asia-south1` (Mumbai) — or your nearest Google region |
| `DB_PASS` | invent a **strong password** for the database (letters + numbers, no spaces) |
| `MAPS_KEY` | paste your **Maps key** from step 4 (or leave empty `""` for now) |
| `GEMINI_KEY` | leave empty `""` unless you have one |

Also note the value of **`SERVICE`** (default `ssd-recovery`) and **`REGION`** — you'll reuse
those exact words later. **Save the file** (keep the same name, don't add `.txt`).

---

## 6. Phase 5 — Run the one command that deploys everything (10–15 min)

1. Open **PowerShell** (Windows) or **Terminal** (Mac) again.
2. Go into the `app` folder. Type `cd ` (with a space), then **drag the `app` folder** from your
   file explorer into the window (it pastes the path), then press Enter. Example:
   ```
   cd C:\Users\you\Desktop\RecoverIQ\app
   ```
3. Run the deploy script:
   - **Windows:**
     ```
     .\deploy\deploy.ps1
     ```
     (If Windows blocks it with a red "running scripts is disabled" message, run this once, then
     retry the line above:)
     ```
     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
     ```
   - **Mac / Linux:**
     ```
     bash ./deploy/deploy.sh
     ```

**What happens now (just watch):** the script turns on Google services, creates the database,
packages the app, and uploads it. This takes **10–15 minutes** and prints a lot of text. That's
normal. If it pauses asking `(y/N)` type `y` and Enter.

✅ **Success looks like this** at the end — a green box with your live address:
```
Deployed:  https://ssd-recovery-xxxxxxxx.run.app
```
**Open that address in your browser.** You should see the RecoverIQ sign-in screen. 🎉
(If it errored instead, go to Troubleshooting (11) — usually it's one value in the settings file.)

> Keep that `https://…run.app` address — that's your app. Bookmark it.

---

## 7. Phase 6 — Create the boss (administrator) login (5 min)

The app is live but empty. Create the first admin login. In your command window, run these two
lines **one at a time** (replace `<SERVICE>` and `<REGION>` with the values from your settings
file — defaults are `ssd-recovery` and `asia-south1`):

```
gcloud run services update <SERVICE> --region <REGION> --set-env-vars SEED_ON_START=1
```
Wait ~1 minute, refresh the app in your browser, then sign in with:
- **Email:** `admin@ssdrecovery.in`
- **Password:** `admin123`

Then immediately turn the seeding off again:
```
gcloud run services update <SERVICE> --region <REGION> --remove-env-vars SEED_ON_START
```

🔒 **Change the admin password now:** the administrator can create and edit users inside the app
(**Team → your account → Edit**). Set a strong password you control.

---

## 8. Phase 7 — Add your staff and load your data (inside the app)

Do all of this by clicking inside the app — no commands:

1. **Team → + Add staff** — add each person and pick their role: **Collections Manager**,
   **Field Agent**, or **Tele-calling Agent**. Give each a strong password. For field agents,
   set their branch, banks, and pincodes (this auto-assigns work to them).
2. **Accounts → Upload** — upload your bank Excel file → **Preview** → **Import & Allocate**.
3. **Accounts → Geocode** — turns addresses into map pins.
4. Send the app address to your staff. On their phone they tap **Install app** (or "Add to Home
   Screen") to use it like a normal app.

---

## 9. Phase 8 — Make it safe for real use (15 min, do before going live)

Run these once (same command window). Replace `<SERVICE>` / `<REGION>` as before:

1. **Turn on production mode** (locks security):
   ```
   gcloud run services update <SERVICE> --region <REGION> --set-env-vars ENVIRONMENT=production
   ```
2. **Restrict the Maps key** so only your app can use it: console → **APIs & Services →
   Credentials →** your key → **Application restrictions → Websites →** add your `https://…run.app`
   address → **Save**.
3. **Set a budget alert:** console → **Billing → Budgets & alerts → Create budget** → set a small
   monthly amount and your email. Google will email you if usage approaches it. (This alerts you;
   it does not cap spend by itself.)
4. **Backups:** Google Cloud SQL takes automatic daily backups. Confirm under **SQL → your
   instance → Backups**.

Optional extras (only if you want them):
- **Save photos safely long-term:** create a storage bucket and set `GCS_BUCKET` (ask your helper).
- **Fingerprint/Face-ID login (passkeys):** set `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` to your
  address. These are done with the same `gcloud run services update … --set-env-vars …` pattern.

---

## 10. Everyday running, cost, and turning it off

- **Nothing to maintain day-to-day.** The app runs on its own. All work (users, data, reports) is
  done inside the app by the administrator and staff.
- **Updating to a newer version of the code:** re-run **Phase 5** (`deploy.ps1`) from the new code
  folder. Your data is safe — it lives in the database, not in the code.
- **Cost:** small for a modest team, billed by Google monthly to your card. Your budget alert
  (section 9) keeps you informed.
- **Pause / stop spending:** console → **Cloud Run → your service → Edit & deploy new revision →**
  set **minimum instances = 0** (it already is), or delete the service to stop entirely. To fully
  stop all cost, also stop or delete the **SQL** instance (this deletes data — take a backup first).

---

## 11. Troubleshooting (common issues → exact fix)

| What you see | What it means | What to do |
|--------------|---------------|------------|
| `gcloud : not recognized` | The tool isn't found yet | Close and reopen the command window; if still failing, reinstall from section 2 and restart the PC |
| `running scripts is disabled on this system` | Windows safety block | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then re-run the deploy line |
| `The billing account ... is not open` / billing error | Billing not linked | Redo section 3 step 4 (link a billing account) |
| `PERMISSION_DENIED` / `API not enabled` | A Google service is off | Re-run the deploy script — it enables them; or wait 1 min and retry |
| Deploy ends without the green `Deployed:` line | A settings value is wrong | Reopen `deploy.ps1`, re-check `PROJECT` matches your Project ID exactly, and `DB_PASS` has no spaces; save; re-run |
| App opens but maps are blank | Maps key missing/restricted | Add the key (section 4) and make sure your app URL is allowed on the key (section 9.2) |
| Can't sign in as admin | Seeding step skipped | Redo section 7 (SEED_ON_START on → sign in → off) |
| "This device is awaiting approval" | Anti-fraud device gate | An admin signs in and approves the new device under **Devices** |

If an error isn't listed here, **copy the last 15 lines** from the command window and send them to
the person who gave you the code. Don't delete anything or retry blindly.

---

## 12. If this still feels too technical — that's okay

You have three easy fallbacks, any of which is fine:

1. **Appoint one person** on your team who's comfortable with computers to follow this guide once.
2. **Hire a freelancer** for ~1 hour (search "Google Cloud Run deployment") and hand them this
   handbook plus the code — the steps are standard.
3. **Ask the provider** who gave you this code to deploy it for you, then you only ever use the
   app (sections 7–8), never the command window.

Once it's deployed, running the business inside RecoverIQ needs **no technical skill at all** —
it's all buttons and screens.
