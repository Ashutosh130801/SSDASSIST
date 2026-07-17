# RecoverIQ — Native Android app

A fully native **Kotlin + Jetpack Compose** Android app for the RecoverIQ collections
platform. It replaces the Capacitor WebView wrapper so that background location tracking
runs in a real Android **foreground service** — reliable even when the app is backgrounded
or the phone is locked.

It talks to the **same FastAPI backend** as the web app. Admins/managers can keep using
the web dashboard; this app also supports every role natively (field agent, tele-caller,
manager, admin).

---

## What's inside

| Layer | Implementation |
|---|---|
| UI | Jetpack Compose + Material 3, role-based bottom navigation |
| Auth | `POST /api/auth/login-json` → JWT, persisted in DataStore; 2FA + device-gate aware |
| Networking | Retrofit + OkHttp + Moshi (codegen). **TLS enforced, certificate pinning, JWT on every request** |
| Background location | `LocationService` foreground service (FusedLocationProvider), `START_STICKY`, restarts on boot |
| Map | osmdroid (OpenStreetMap) — same tiles as the web app, no Google Maps key |

Package / app id: `in.recoveriq.app`.

### Roles → screens
- **Field agent (`fos`)** — On-duty toggle (starts/stops live tracking), My Cases, Profile.
- **Tele-caller** — Call queue (tap to dial), PTP tracker, Profile.
- **Manager / Admin** — Dashboard KPIs, Live agent map, All cases, Profile.

> Scope note: the field-agent tracking flow and the core role screens are fully wired to
> the backend. Heavier admin modules (litigation, leave, devices, communication templates)
> are best left on the web dashboard or added here incrementally — each is a new Compose
> screen calling an endpoint that already exists.

---

## Open & run in Android Studio

1. **Open the folder** `android-native/` in Android Studio (Koala / 2024.1 or newer).
   On first sync, Android Studio downloads Gradle 8.9 (from `gradle/wrapper/gradle-wrapper.properties`)
   and generates the Gradle wrapper automatically. Let the sync finish.
2. **Point it at your backend.** Either edit the default in `app/build.gradle.kts`
   (`BASE_URL`) or, better, add to `gradle.properties` (this file is git-ignored for secrets):
   ```
   BASE_URL=https://your-backend-url/        # must end with a slash
   CERT_PIN=                                  # leave empty for now (see below)
   ```
3. **Run** on a device or emulator (▶). Sign in with a real RecoverIQ account.
4. As a **field agent**, flip **On Duty** → grant location **"Allow all the time"** and
   notifications, then allow **unrestricted battery**. A persistent notification confirms
   tracking is live. Background the app or lock the phone — pings keep posting to
   `/api/tracking/ping` and appear on the admin live map.

### Watching it work
Logcat tag **`RQTrack`** shows the service lifecycle and each fix/POST; **`RQNet`** shows
whether certificate pinning is active.

---

## Certificate pinning (recommended before production)

Pinning makes the app trust **only your server's certificate**, blocking man-in-the-middle
interception. It's off until you supply a pin.

1. Get your server's SPKI pin (run on any machine with `openssl`, replace the host):
   ```
   openssl s_client -connect your-backend-host:443 -servername your-backend-host < /dev/null 2>/dev/null \
     | openssl x509 -pubkey -noout \
     | openssl pkey -pubin -outform der \
     | openssl dgst -sha256 -binary \
     | openssl enc -base64
   ```
2. Put it in `gradle.properties` as `CERT_PIN=sha256/<that-base64>=`.
3. Rebuild. `RQNet` will log `Certificate pinning enabled`.

> Pin the **intermediate CA** key (or add a backup pin) so certificate renewal doesn't lock
> users out. Update the pin whenever you change CAs.

---

## Build an installable APK without Android Studio (CI)

`.github/workflows/android-native-build.yml` builds the APK on GitHub Actions and publishes
it to the **`android-native-latest`** release.

- Add repo secret **`APP_URL`** = your backend URL (and optionally **`CERT_PIN`**).
- Run the workflow (Actions → *Build Native Android App* → *Run workflow*), or push a change
  under `android-native/`.
- On the phone, open the `android-native-latest` release page and tap `RecoverIQ-native.apk`.

---

## Security model (why not Signal E2EE)

Location telemetry must be **readable by your server and admins** — that's the whole point
of the live map. End-to-end encryption (Signal protocol) makes data readable *only* by the
two endpoints and opaque to the server, which would blank the admin map. The correct model
here, implemented in this app, is **TLS in transit + certificate pinning + JWT auth**, with
access control enforced server-side. (If you later add agent-to-agent chat, that's the right
place for E2EE — not for tracking.)
