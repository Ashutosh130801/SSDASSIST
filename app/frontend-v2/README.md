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

- **Round 1 modules** (`src/modules/`, identical in v2 / v3 / v4, styled by each template):
  - My Accounts (FOS), Joint Cases, Calling queue, My Performance, My Work Queue
  - Escalations, My Team (team lead), Leave (apply, approvals, history, balances), Change Requests
  - Devices, Audit Log, Activity, RTSB, Live Monitor
- **Round 2 modules:**
  - **Team:** branch cards, FOS / caller / team-lead directories, branch detail with analytics, transfer, live route, route history and staff editing
  - **MIS:** overview (KPIs, projection, eight charts, target), leaderboards and all 16 tables with Excel/print, full sheet, cycle-wise and pivot views
  - **Live Sheet:** multi-user live editing with presence, column presets, data/formula columns, per-column filters, sort, drag-reorder, totals, formula bar, CSV/Excel
  - Complex classic forms are reused, not duplicated: the GPS-camera visit, staff editor, employee profile, performance and audit-detail panels open through `__riqClassic.openPanel()` (patched in by `classic_host.py`). Pages refresh live through `__riqClassic.subscribe()` (same WebSocket as classic).
- **Round 3:** no more "Full module" buttons — every native screen carries the complete classic feature set:
  - Accounts (banks → products → locations → cases, all filters, re-allocate / joint / transfer / delete, removed cases, upload, DPR, undo upload, corrections, ViciDial push, campaign, auto-allocate, geocode, export, reset, segment fix, portfolio Excel)
  - PTP Tracker, Attendance (day / month / salary-cycle range, role + location + status filters, live ViciDial state, print, CSV, Excel, FOS visit reports), Dashboard (MIS highlights, dispositions, partial payments)
  - Manpower, My E-ID, Bank Feedback, Litigation, Communication, Monthly Archive, My Portfolios (team lead), Security, Help & Support / Support Inbox
  - Field Tracking (v2): FOS roster, multi-officer route export, flagged visits, geocoding, day-visit Excel
  - Every case opens the full case screen; complex classic forms open inside the new UI, themed, through `__riqClassic.openPanel('component' | 'inline' | 'tools', …)` (registry in `classic_host.py`, checked at startup). Popups close on Escape and when you change screen.
- **Field TL** (role key `teamfollower`, IDs `FTL…`): HR / admin / HO create one in Manpower (role “Field TL”, or tick “Also a Field TL” on a team lead / FOS / caller, which issues a second FTL id and a view switch) and pick their FOS / callers under **Manpower → Field TL groups**. The Field TL page shows each member’s complete performance across every portfolio — cases, collections, visits, calls, attendance, live route and history — read-only.
- **Round 4:** AI Assist (chats, charts, tables, files, actions), Services (toggles + settings/keys + AI provider test), Add-ons hub, Connections (Autodialer + full ViciDial setup) and a native locked Salary & Payslips screen — in v2 / v3 / v4. Each add-on's own workspace opens in the module area in the active theme.
- **Field Tracking in v3** (Soft Clay) — the same live map, roster, route replay and My Route as v2, moulded in clay, light and dark.
- **Dark mode for everything classic:** popups, drawers, forms, tables, the check-in card and add-on screens follow dark mode in v2 and v3 (status / heat-map cells keep their colour with dark text).
- (superseded) Modules not yet rebuilt (Manpower, Payroll, Litigation, Bank Feedback, Connections, AI Assist, etc.) run the classic screen under a full per-template skin (`classic-skin.css`): tiles, chips, badges, tables, modals and entrance motion follow the template.

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

## Round 5 — floating widgets + every add-on rebuilt natively (v2 / v3 / v4)
- **Messages** (`modules/FloatWidgets.jsx → FloatChat`): chats list, new-chat picker with role filter + search, threads with stickers and read ticks,
  Office desk, broadcast (select many), Head-Office chat requests, unread badge, voice call (hands off to the classic WebRTC call via `__riqClassic.startCall`).
- **AI companion** (`FloatBot`): same companions as classic (`modules/Pets.jsx`, ported 1:1 + `styles/pets.css`), drag to move, moods, naps,
  companion picker, page reading of the native page/modals (`[data-ai-skip]` respected), charts/files/actions via the shared `AiMsg`.
- In the new UIs the classic ChatWidget + AiBot are not rendered (patched in `backend/app/classic_host.py` only — the classic UI at `/` is unchanged).
  Voice calls and broadcast popups still come from the classic layer.
- **Add-ons** open at `/addons/:key` (`modules/AddonHost.jsx`): Compliance, Payment links, Outreach (`AddonsA.jsx`), Settlement, Smart allocation,
  Legal notices (`AddonsB.jsx`), Analytics, Billing, Skip tracing, Open API (`AddonsC.jsx`). Shared kit: `AddonKit.jsx` (themed prompt/confirm
  replace browser dialogs). QR codes use the classic QR library through `__riqClassic.qrDataUrl`.
