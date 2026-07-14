# RecoverIQ — Android app with always‑on background location

This wraps your existing web app in a native Android shell that keeps sending the field
officer's location to your server **even when the phone is locked or the app is in the
background** — using a foreground service (the officer sees a persistent "on duty" notification,
which is also required by Google Play and by law for transparency).

It changes **nothing** about your web app or backend. The Android app just loads your live site
and adds the background‑location capability. Everything else (login, cases, maps, visits) is the
same. The app pings the same endpoint you already have: `POST /api/tracking/ping`.

> **Where the build happens:** compiling an `.apk` needs the Android SDK, so it is done on a
> computer with **Android Studio** (Windows/Mac/Linux) — it can't be built inside this chat. The
> steps below are copy‑paste. Budget ~30–45 min the first time (mostly installing Android Studio).

---

## 0. Install once
- **Node.js 18+** — https://nodejs.org
- **Android Studio** (includes the Android SDK) — https://developer.android.com/studio
- **JDK 17** (Android Studio bundles one; otherwise install Temurin 17)

## 1. Point the wrapper at your live app
Open `app/mobile/capacitor.config.json` and set `server.url` to the URL where your app is running
(your Cloud Run URL, VPS domain, or even your tunnel URL for testing), e.g.:
```json
"server": { "url": "https://recoveriq-xxxx.run.app", "cleartext": false }
```
(Use `"cleartext": true` only if you must point at a plain `http://` address for local testing.)

## 2. Install and add Android
From the `app/mobile` folder in a terminal:
```
npm install
npx cap add android
npx cap sync
```

## 3. Add the location permissions
Open `app/mobile/android/app/src/main/AndroidManifest.xml` and paste these lines **inside** the
`<manifest>` tag, above `<application>` (also see `android-permissions.xml` in this folder):
```xml
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```
Then run `npx cap sync` again.

## 4. Build the APK
Either from the terminal:
```
cd android
./gradlew assembleDebug        # Windows: gradlew.bat assembleDebug
```
The installable file appears at
`app/mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

Or with the IDE:
```
npx cap open android
```
then in Android Studio: **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.

## 5. Install on the officer's phone
- Copy the `.apk` to the phone and open it (allow "install from unknown sources"), **or** connect
  the phone by USB and use **Run ▶** in Android Studio.
- On first launch, when it asks for location, choose **"Allow all the time"** (not just "while
  using") — this is what enables background tracking. Also allow notifications.

That's it. The officer logs in normally; while on duty the app shows an "on duty" notification and
streams their location to your Live Map and the Team → 📍 Live route view, even with the screen off.

---

## How it works (for your developer)
- The web app detects Capacitor (`window.Capacitor`) and, when native, starts
  `@capacitor-community/background-geolocation`'s `addWatcher`, POSTing each location to
  `/api/tracking/ping` with the logged‑in officer's token. In a normal browser it falls back to
  the foreground‑only `watchPosition` (unchanged).
- The plugin runs an Android **foreground service**, so the OS keeps delivering locations when the
  app is backgrounded or the screen is locked. The persistent notification is mandatory for this.

## Store release / no‑laptop options
- For a signed **release** build (`assembleRelease`) you'll create a keystore — standard Android
  signing; Android Studio has a wizard (**Build → Generate Signed Bundle/APK**).
- No computer with Android Studio? You can build in the cloud with **GitHub Actions** or **Ionic
  Appflow** — ask and I'll add a ready CI workflow that outputs the APK on every push.

## Play Store note
Background location requires a short **prominent‑disclosure + consent** screen and a Play Console
declaration form. Since this is an internal workforce app, you can also distribute the APK directly
to staff (no Play Store) — which is the common approach for field‑collections teams.
