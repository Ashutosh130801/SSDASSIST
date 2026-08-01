# Custom Domain + Always-On — For Your Existing Windows Setup

## Your Current Setup (Already Working ✅)

```
External PC (Windows):
  ├─ Git clone of SSDASSIST
  ├─ run_local.bat → Python venv → FastAPI + SQLite on port 8000
  ├─ Auto-pull bat → Windows Task Scheduler → git pull every 10 min
  └─ Accessible at http://localhost:8000 (local only)
```

**What you need now:**
1. Make it reachable from the internet at `https://app.yourdomain.in` ← **Cloudflare Tunnel**
2. Keep the PC and app running 24/7, auto-restart after crash/reboot ← **Windows services + power settings**

---

## Part 1 — Connect to Custom Domain (Cloudflare Tunnel)

> This makes your external PC reachable at `https://app.yourdomain.in` from anywhere — phones, laptops, any network. Free HTTPS. No router port-forwarding. No static IP needed.

### Step 1.1 — Buy a domain (if you don't have one)

- Buy from **GoDaddy**, **Namecheap**, **Cloudflare Registrar**, or any registrar
- Example: `ssdenterprises.in` (~₹700–900/year)
- If you already have one, skip to Step 1.2

### Step 1.2 — Move your domain's DNS to Cloudflare (free)

1. Go to [cloudflare.com](https://cloudflare.com) → **Sign up** (free account)
2. Click **Add a site** → type your domain (e.g. `ssdenterprises.in`)
3. Select the **Free** plan → Continue
4. Cloudflare shows you **two nameservers**, for example:
   ```
   anna.ns.cloudflare.com
   bob.ns.cloudflare.com
   ```
5. Go to **your domain registrar** (where you bought the domain):
   - Find **DNS** or **Nameservers** settings
   - **Replace** the existing nameservers with Cloudflare's two
   - Save
6. Back in Cloudflare → click **Check nameservers**
7. ⏳ Wait **15 minutes to a few hours** — Cloudflare shows **"Active"** when ready

> [!TIP]
> You don't lose your domain or email. You're just telling the internet "Cloudflare manages the DNS for this domain now." Everything else stays the same.

### Step 1.3 — Install cloudflared on the external PC

On the **external PC**, open PowerShell **as Administrator**:

```powershell
# Download the installer
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi" -OutFile "$HOME\Downloads\cloudflared.msi"

# Install silently
Start-Process msiexec.exe -ArgumentList "/i `"$HOME\Downloads\cloudflared.msi`" /quiet" -Wait
```

**Close and reopen PowerShell**, then verify:

```powershell
cloudflared --version
```

> If it says "not recognized", the installer put it in `C:\Program Files (x86)\cloudflared\`. Either:
> - Use the full path: `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version`
> - Or add that folder to your PATH: Settings → search "environment variables" → System variables → Path → Edit → Add the folder

### Step 1.4 — Log in to Cloudflare and create a tunnel

```powershell
cloudflared tunnel login
```

This opens a browser window. **Select your domain** (e.g. `ssdenterprises.in`) and click **Authorize**.

Now create the tunnel:

```powershell
cloudflared tunnel create recoveriq
```

It prints something like:

```
Created tunnel recoveriq with id a1b2c3d4-e5f6-7890-abcd-1234567890ef
```

📝 **Write down this Tunnel ID** — you need it in the next steps.

### Step 1.5 — Route your subdomain to the tunnel

```powershell
cloudflared tunnel route dns recoveriq app.ssdenterprises.in
```

Replace `ssdenterprises.in` with **your** domain. This creates a DNS record in Cloudflare automatically.

> Using `app.` as a subdomain is recommended — it keeps your root domain free for a website/email later.

### Step 1.6 — Create the tunnel config file

```powershell
notepad "$HOME\.cloudflared\config.yml"
```

Notepad opens. Paste this (replace the 3 placeholders):

```yaml
tunnel: PASTE-YOUR-TUNNEL-ID-HERE
credentials-file: C:\Users\YOURUSERNAME\.cloudflared\PASTE-YOUR-TUNNEL-ID-HERE.json

ingress:
  - hostname: app.ssdenterprises.in
    service: http://localhost:8000
  - service: http_status:404
```

**Example** (with real values filled in):

```yaml
tunnel: a1b2c3d4-e5f6-7890-abcd-1234567890ef
credentials-file: C:\Users\Sahoo\.cloudflared\a1b2c3d4-e5f6-7890-abcd-1234567890ef.json

ingress:
  - hostname: app.ssdenterprises.in
    service: http://localhost:8000
  - service: http_status:404
```

Save and close.

### Step 1.7 — Test the tunnel (before making it permanent)

```powershell
cloudflared tunnel run recoveriq
```

This runs the tunnel in the foreground. **While it's running**, open a browser on your **phone or any other device** and go to:

```
https://app.ssdenterprises.in
```

You should see the **RecoverIQ login page with a padlock** 🔒.

If it works, press **Ctrl+C** to stop it. We'll make it permanent in the next step.

> [!WARNING]
> **If it doesn't work**, check:
> - Is `run_local.bat` running? The app must be listening on `localhost:8000`
> - Did Cloudflare show "Active" for your domain? (Step 1.2)
> - Is the `config.yml` correct? Check the tunnel ID, credentials-file path, and hostname

### Step 1.8 — Install the tunnel as a Windows Service (auto-starts on boot)

Open PowerShell **as Administrator**:

```powershell
cloudflared service install
```

> [!IMPORTANT]
> **Critical step**: When `cloudflared` runs as a Windows service, it runs as the **SYSTEM** account, which has a different home folder. You must copy your config and credentials there:

```powershell
# Still in Admin PowerShell:
$systemCF = "C:\Windows\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Path $systemCF -Force

# Copy your config and credentials
Copy-Item "$HOME\.cloudflared\config.yml" $systemCF\
Copy-Item "$HOME\.cloudflared\*.json" $systemCF\
```

Now edit the **copied** config to fix the credentials path:

```powershell
notepad "$systemCF\config.yml"
```

Change the `credentials-file` line to use the SYSTEM profile path:

```yaml
credentials-file: C:\Windows\System32\config\systemprofile\.cloudflared\PASTE-YOUR-TUNNEL-ID-HERE.json
```

Save. Then start the service:

```powershell
Start-Service cloudflared
Get-Service cloudflared
```

Should show **Running**.

### Step 1.9 — Verify!

Open `https://app.ssdenterprises.in` on your phone (use mobile data, NOT the same WiFi) — login page with padlock = **done!** 🎉

---

## Part 2 — Keep the External PC Always On

### Step 2.1 — Never sleep

Open **Settings → System → Power & sleep** (or Power & battery on Win 11):

| Setting | Set to |
|---|---|
| **Screen** → Turn off after | Your choice (screen off is fine — doesn't affect the app) |
| **Sleep** → PC goes to sleep after | **Never** |

**If it's a laptop:**
- Settings → System → Power → **Additional power settings** (right side) → **Choose what closing the lid does**
  - "When I close the lid" → **Do nothing** (for both plugged in and on battery)
  - Click **Save changes**

### Step 2.2 — Disable automatic reboot from Windows Updates

Windows sometimes reboots overnight for updates. Prevent this:

Open PowerShell **as Administrator**:

```powershell
# Tell Windows not to auto-reboot while someone is logged in
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f

# Set active hours to the maximum range (your work hours)
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 6 /f
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd /t REG_DWORD /d 2 /f
```

Also in **Settings → Windows Update → Advanced options**:
- Set **Active hours** manually: 6 AM to 2 AM (maximum range)

### Step 2.3 — Auto-start the app on boot / after crash

Your `run_local.bat` needs to start automatically when the PC boots (or after a crash/reboot). Create a **wrapper script** that starts the app in the background.

**Create `C:\Users\<username>\start_ssd_server.vbs`** (this runs the bat file hidden, no visible window):

Open Notepad and paste:

```vbs
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\<username>\SSDASSIST\app\backend\run_local.bat""", 0, False
```

Replace `<username>` with the actual Windows username on that PC. Save as `start_ssd_server.vbs` in the home folder.

**Now set it to run on boot using Task Scheduler:**

1. Press **Win + R** → type `taskschd.msc` → Enter
2. Click **Create Task** (not "Basic Task" — we need more control)
3. **General** tab:
   - Name: `SSDASSIST Server`
   - ✅ **Run whether user is logged on or not**
   - ✅ **Run with highest privileges**
   - Configure for: **Windows 10** (or 11)
4. **Triggers** tab → **New**:
   - Begin the task: **At startup**
   - Delay task for: **30 seconds** (gives the network time to connect)
   - ✅ Enabled
   - Click OK
5. **Actions** tab → **New**:
   - Action: **Start a program**
   - Program/script: `wscript.exe`
   - Add arguments: `"C:\Users\<username>\start_ssd_server.vbs"`
   - Click OK
6. **Settings** tab:
   - ✅ **If the task fails, restart every: 1 minute**
   - Attempt to restart up to: **3 times**
   - ❌ Uncheck "Stop the task if it runs longer than"
   - If the task is already running: **Do not start a new instance**
7. Click **OK** — enter the PC's Windows password when prompted

### Step 2.4 — Auto-start the auto-pull task on boot too

Your existing auto-pull (git pull every 10 min) should already be in Task Scheduler. Double-check:

1. Open **Task Scheduler** → find your auto-pull task
2. In **Triggers**, make sure you also have an **"At startup"** trigger (in addition to the "repeat every 10 min" one)
3. In **Settings**, ✅ **Run whether user is logged on or not**

### Step 2.5 — Handle app restart after auto-pull

> [!IMPORTANT]
> Your auto-pull does `git pull` every 10 minutes, but the **running app doesn't pick up the new code** — FastAPI is already loaded into memory. You need to **restart the app** after pulling new code.

Update your auto-pull bat to also restart the server. Here's what it should look like:

```batch
@echo off
cd /d "C:\Users\<username>\SSDASSIST"

REM Pull latest code
git pull origin main

REM Check if git pull actually changed anything
git diff --stat HEAD@{1} HEAD -- app/ >nul 2>&1
if %errorlevel%==0 (
    echo No changes in app/ — skipping restart.
    exit /b 0
)

REM Kill the running Python server
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" >nul 2>&1
taskkill /F /IM uvicorn.exe >nul 2>&1

REM Wait a moment
timeout /t 3 /nobreak >nul

REM Restart the server
wscript.exe "C:\Users\<username>\start_ssd_server.vbs"

echo App restarted with new code.
```

> The `taskkill` may kill other Python processes. A simpler approach: just always restart the app after `git pull`, even if nothing changed — uvicorn starts fast (~5 seconds).

**Simpler version** (always restarts):

```batch
@echo off
cd /d "C:\Users\<username>\SSDASSIST"
git pull origin main
taskkill /F /IM python.exe >nul 2>&1
timeout /t 3 /nobreak >nul
wscript.exe "C:\Users\<username>\start_ssd_server.vbs"
```

---

## Part 3 — Summary of What's Running on the External PC

After completing all steps, the external PC has:

| What | How it runs | Starts on boot? |
|---|---|---|
| **FastAPI app** (port 8000) | `run_local.bat` via Task Scheduler | ✅ Yes (30 sec delay) |
| **Cloudflare Tunnel** | Windows Service (`cloudflared`) | ✅ Yes (automatic) |
| **Auto-pull from GitHub** | Your bat file via Task Scheduler (every 10 min) | ✅ Yes |
| **SQLite database** | File on disk (`ssd_local.db`) | N/A (persistent) |

### What happens in different scenarios

| Event | What happens |
|---|---|
| **Power cut → PC boots back up** | Windows logs in → Task Scheduler starts the app (30 sec delay) → Cloudflare tunnel service starts automatically → Site is back online in ~1 min |
| **You push code from your dev PC** | Within 10 min, auto-pull grabs it → app restarts → changes are live |
| **Internet drops temporarily** | Tunnel reconnects automatically when internet comes back — `cloudflared` handles this |
| **App crashes** | Task Scheduler retries up to 3 times (1 min apart) |

### Your workflow

```
1. Edit code on your dev PC
2. git add -A && git commit -m "..." && git push origin main
3. Wait up to 10 minutes (your auto-pull interval)
4. Refresh https://app.ssdenterprises.in — changes are live
```

---

## Quick Troubleshooting

| Problem | Fix |
|---|---|
| Site not loading at all | On external PC: check `Get-Service cloudflared` is Running. Check if the app is running: open `http://localhost:8000` on that PC. |
| Cloudflare says "DNS not found" | Nameservers haven't propagated yet. Wait up to 24 hours. Check Cloudflare dashboard shows "Active". |
| `localhost:8000` works but domain doesn't | Tunnel issue. Check `config.yml` — hostname must match exactly. Check credentials-file path in the SYSTEM profile copy. Restart: `Restart-Service cloudflared` |
| App not restarting after git pull | Check your auto-pull bat includes `taskkill` and restart commands. Check Task Scheduler → right-click task → "Last Run Result". |
| PC went to sleep | Settings → Power → Sleep → **Never**. For laptops: lid close → Do nothing. |
| "Port 8000 already in use" | Previous instance didn't stop. Run `taskkill /F /IM python.exe` then restart. |
| HTTPS certificate error | Wait 5–10 min — Cloudflare provisions the cert automatically. If it persists, check Cloudflare dashboard → SSL/TLS → set to **Full**. |

---

## Is Your 10-Minute Auto-Pull Setup OK?

✅ **Yes, it works fine.** It's simple and reliable. The only thing to add:

> [!IMPORTANT]
> **Restart the app after pulling.** Right now your auto-pull probably just does `git pull`. The running Python process doesn't reload code from disk — you must kill and restart it. See Step 2.5 above.

**If you want faster deploys** (instant instead of up to 10 min), you can later switch to a GitHub Actions self-hosted runner (from the previous guide). But 10 min is perfectly fine for most use cases — your field officers won't notice.
