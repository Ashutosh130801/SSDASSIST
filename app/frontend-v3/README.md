# RecoverIQ — Soft Clay template (frontend-v3, served at `/v3/`)

Full neumorphism. Everything is moulded from one soft surface:

- raised panels and pressed-in inputs
- a pressed active-nav state
- an icon rail that expands on hover
- calm floating clay forms in the background, with no WebGL

Light and dark ("clay night") modes are available, and the default palette is Azure blue.

Styles: `src/styles/clay.css`, layered over the shared `surfaces.css`. The classic modules are re-skinned to match in `src/styles/classic-skin.css`.

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
- **Separate settings.** Theme, palette and sidebar preferences are stored separately from v2 (`riq_v3_*`).

## Develop / build

```bash
npm install
npm run dev     # :5173, proxies /api /assets /downloads /v2/classic to 127.0.0.1:8000
npm run build   # writes dist/ — commit it (served by the backend / Docker image)
```
