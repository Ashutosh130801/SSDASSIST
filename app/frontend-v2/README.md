# RecoverIQ: redesigned UI (frontend-v2)

The redesigned UI sits alongside the classic one. **The classic UI at `/` is not modified in any way.** The new UI is served at one extra URL:

| URL | Edition | Default look |
|---|---|---|
| `/v2/` | **Enterprise** | Azure: royal blue and white (light), deep navy (dark) |

The Premium look (Sapphire, dark-first) is a toggle in the sidebar footer. Two more templates live in their own folders: **`/v3/` Soft Clay** (`frontend-v3`) and **`/v4/` Spatial 3D** (`frontend-v4`). Users can change the colour palette from the top bar (Azure, Sapphire, Lagoon, Ocean, Emerald Gold, Sunset, Noir Orchid, Aurum) and switch light/dark. The sign-in screen always uses the edition's blue palette.

## Nothing is left behind

The new UI runs the **classic runtime** in a transparent layer for the whole session:

- **Every module.** The menu is read live from the classic app, so it follows each role and the Services on/off switches. Screens that haven't been redesigned open at `/#/m/<id>` and show the full classic module inside the new frame, re-skinned in the active palette.
- **Everything that lives in the classic shell keeps running:**
  - chat widget, AI bot, voice calls, broadcast popups
  - attendance gate / check-in, idle logout, GPS pings
  - telecaller screen-pop, guided tour, help button
  - the full case drawer: log call, visit or payment, PTP, history
- **Classic top-bar shortcuts are in the new top bar:** To-Do, RTSB, Live Monitor, Attendance, Add-ons, Services (admin) and Print liner (FOS). Downloads, view switching and the tour are in the user menu.
- **Clicks pass through.** v2 stays clickable except where classic is actually drawing something (a widget, popup or the module area).

The runtime is a **patched copy generated on the fly** by `backend/app/classic_host.py` from the live `frontend/app.jsx` and served at `/v2/classic/`. When the classic app changes, the new UI picks the change up automatically, and there's nothing to rebuild. If a classic change ever breaks a patch, that endpoint returns 503 and names the patch.

## Redesigned natively

- **Login.** Glass card, 3D orb, light/dark toggle, 2FA, app downloads.
- **Dashboard** (management roles). Bento layout:
  - hero card with an animated ring and a WebGL liquid core
  - clay KPI tiles with sparklines
  - collections trend, account status, pipeline, portfolio by bank, field leaderboard
- **Accounts** (management roles). List with filters and a case side-panel. Opening the full case brings up the classic case drawer.
- **PTP Tracker.**
- **Field Tracking (v2 only).** Admins, managers and head office get a full-height live map with:
  - Map/Satellite tiles and a night map in dark mode
  - a glass roster with live/idle/offline counts, km today, search, branch and date filters
  - pulsing agent markers
  - an agent card with call/WhatsApp, 30-day history chips, a gradient route trail and day replay
  - visits with GPS-camera photos
- **My Route (FOS, v2 only).** Today's trail, your accounts as status-coloured pins, a nearest-first worklist with Navigate, and opening the full case to log a visit or payment.
- Both Field Tracking pages use the existing APIs only, and each has a **Full module** button for the classic tools (geocoding, roster, exports, flagged visits).
- **Attendance** day board (management/HR), including the FOS daily and monthly reports.

Each native page has a **Full module** button that opens the complete classic module.

## Design system

- **Glassmorphism:** frosted sidebar, top bar, cards and menus with gradient hairlines.
- **Claymorphism:** puffy KPI tiles, icon chips, primary buttons, active nav and the segmented control.
- **Motion:**
  - WebGL aurora backdrop (raw shader, no 3D library)
  - raymarched 3D orb
  - 3D tilt with glare on hover
  - count-up numbers, staggered entrances, self-drawing sparklines
- **Fallbacks:** reduced-motion is respected, rendering pauses in hidden tabs, and there's a CSS fallback when WebGL is unavailable.
- Palettes live in `src/lib/palettes.js`. Each one drives accents, tones, charts, hero, backdrop and the classic skin.

## Develop / build

```bash
cd app/frontend-v2
npm install
npm run dev     # http://localhost:5173 — proxies /api, /assets, /downloads, /v2/classic to 127.0.0.1:8000
npm run build   # writes dist/ — commit dist/ (served by the backend / Docker image)
```

To redesign another screen natively:

1. Add a page.
2. Add a `<Route>` in `main.jsx`.
3. Add its id to `nativeFor()` in `lib/nav.js`.

Until then, the classic module is shown in its place.
