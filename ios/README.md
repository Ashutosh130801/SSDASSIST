# RecoverIQ for iPhone — native SwiftUI

Fully native port of the Android app (`android-native/`) — same screens, roles, API calls and rules.
iOS 16+, SwiftUI, Swift Charts, MapKit, Core Location. No third-party libraries.

| Folder | Contents |
|---|---|
| `RecoverIQ/App` | `@main` app, AppDelegate (background-location relaunch), `AppState` (= AuthViewModel) |
| `RecoverIQ/Core` | Models (all Kotlin data classes), API client + every endpoint, Keychain session, WebSocket realtime, updater, file sharing |
| `RecoverIQ/Location` | Background FOS tracking (`LocationTracker`), one-shot GPS (`LocationOnce`) |
| `RecoverIQ/UI` | Theme, shared components, case card, actions (call/WhatsApp/maps/UPI), MapKit view, QR, guided tour |
| `RecoverIQ/Nav` | Login (2FA), view picker, forced password change, role-based side menu (`NavEntries`) |
| `RecoverIQ/Features` | `Fos`, `Detail`, `Caller` (caller/TL/portfolio/performance/team), `Admin` (dashboards, live map, MIS), `HR`, `Collab` (chat, RTSB, to-do, monitor, legal, comms, devices, activity, security, AI) |

Porting rules and the screen contract: `NATIVE_PORT.md`, `PORTERS_API.md`.

## Build (no Mac needed)
GitHub → **Actions → Build iOS App (unsigned IPA)** (runs automatically on pushes under `ios/`). XcodeGen generates the
project on a macOS runner, Xcode builds it unsigned, and the workflow publishes `RecoverIQ.ipa`, `ios.json` and
`ios-source.json` to `app/frontend/downloads/` (→ 🍎 iPhone app button on the login page) plus the `ios-latest` release.
If a build fails, open the `xcodebuild-log` artifact.

## Install
SideStore / AltStore / Sideloadly with a free Apple ID (7-day refresh, 3 apps) — or a paid developer account for 1-year installs.
Field agents: location **Allow While Using → Change to Always Allow** so tracking keeps running when locked.
