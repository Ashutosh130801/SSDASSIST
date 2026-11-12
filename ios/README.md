# RecoverIQ for iPhone (hybrid)

A native iOS shell that opens the live RecoverIQ web app, with the parts a browser can't do done natively:

| Native (Swift) | File |
|---|---|
| Background FOS route tracking (keeps running when locked; iOS relaunches it after a restart / significant move) | `LocationTracker.swift` |
| `navigator.geolocation` from Core Location (visit GPS stamps, check-in — no repeated web prompts) | `GeoBridge.swift` |
| Bridge `window.RIQNative` (auth sync, tracking start/stop, file save, settings) | `Bootstrap.swift`, `WebViewController.swift` |
| Excel / PDF / CSV downloads → iOS share sheet (Save to Files, WhatsApp, Excel…) | `WebViewController.swift` |
| tel: / WhatsApp / Maps links, JS alert/confirm/prompt, camera + mic for the site | `WebViewController.swift` |
| Session token in the Keychain, device id kept for check-in device pinning | `NativeStore.swift` |
| "Update available" → one-tap update through SideStore / AltStore | `Updater.swift` |

## Build (no Mac needed)

GitHub → **Actions → Build iOS App (unsigned IPA) → Run workflow** (or push a change under `ios/`).
It runs on a macOS runner, generates the Xcode project with XcodeGen, builds **unsigned**, and publishes:

* `app/frontend/downloads/RecoverIQ.ipa` + `ios.json` + `ios-source.json` (served by RecoverIQ → **🍎 iPhone app** button on the login page)
* the `recoveriq-ios-ipa` artifact and the `ios-latest` GitHub Release.

Server URL: `app_url` input → `APP_URL` repo secret → default in `project.yml`.
If the build fails, download the `xcodebuild-log` artifact.

## Install on an iPhone (free Apple ID)

1. Install **SideStore** (sidestore.io — one-time setup with a computer) or AltStore.
2. On the iPhone open RecoverIQ in Safari → login page → **🍎 iPhone app** → **Add RecoverIQ to SideStore** (or download the `.ipa` and add it in SideStore → My Apps → +).
3. Sign in. Field agents: location **Allow While Using → Change to Always Allow**.

Free Apple ID limits (Apple's rules): refresh every **7 days** in SideStore, max 3 sideloaded apps, no push notifications (local reminders only).
Swiping the app away pauses live tracking (iOS rule) — a reminder notification asks the agent to reopen it; significant-move relaunch still records ~every 500 m.
A paid Apple Developer account ($99/yr) removes the 7-day refresh.
