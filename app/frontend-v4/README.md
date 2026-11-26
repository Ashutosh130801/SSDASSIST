# RecoverIQ — Spatial 3D template (frontend-v4, served at `/v4/`)

A dark, holographic 3D workspace:

- **The world:** a glowing grid floor runs to the horizon, orbit rings and stars sit in the background, and the WebGL aurora and particle terrain move behind them.
- **Panels:** holographic glass with light-catching edges. They fly in from depth on every route change and lift with a glow on hover.
- **Layout:** the sidebar is a 3D dock that squares up when you reach for it. Dashboard side columns angle toward the centre.
- **Overlays:** drawers, menus and the command palette swing in on 3D hinges.
- **Classic modules:** they follow the same template. They render as dark holographic panels with the same 3D entrance, and the classic modals and chat panels are re-skinned too.

The template is dark-only, the default palette is Sapphire, and `prefers-reduced-motion` turns the motion off.

Styles: `src/styles/spatial.css` + `src/styles/classic-skin.css`.

## Same architecture as v2 — nothing left behind

- **Every module.** The menu is read live from the classic app, so it follows each role and the Services switches. Redesigned screens run natively; every other screen (`/#/m/<id>`) is the full classic module inside this template's frame and skin.
- **Shell features keep running.** The classic runtime layer keeps all of these alive:
  - chat and the AI bot
  - voice calls and broadcasts
  - check-in / idle logout and GPS pings
  - screen-pop, the guided tour and the help button
  - the full case drawer
- **Classic is untouched.** The classic app at `/` is never modified. The runtime is a copy patched on the fly by the backend (`/v2/classic/*`, shared by all templates).
- **Audited.** Every role (admin, manager, head office, team lead, FOS, telecaller, back office, HR, staff, IT support view) was checked against every screen plus the top-bar shortcuts.
- **Separate settings.** Theme, palette and sidebar preferences are stored separately from v2 (`riq_v4_*`).

## Develop / build

```bash
npm install
npm run dev     # :5173, proxies /api /assets /downloads /v2/classic to 127.0.0.1:8000
npm run build   # writes dist/ — commit it (served by the backend / Docker image)
```
