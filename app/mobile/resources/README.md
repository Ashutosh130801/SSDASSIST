# App icon & splash for the Android build

Drop two images in this `resources/` folder and the cloud build will turn them into all the
Android launcher-icon sizes automatically (via `@capacitor/assets`):

- **`icon.png`** — your logo, **1024 × 1024 px**, square PNG. Keep important detail in the middle
  ~66% (Android rounds/masks the edges into circles/squircles).
- **`splash.png`** *(optional)* — the launch screen, **2732 × 2732 px**, square, with the logo
  centered on a solid background.

Then commit + push. The next build uses them. No images here = the default Capacitor icon.

The app **name** under the icon comes from `appName` in `../capacitor.config.json`.
