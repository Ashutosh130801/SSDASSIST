# RecoverIQ iOS — native SwiftUI port of `android-native/` (spec for every porter)

Goal: **full feature parity** with the Kotlin/Compose app in `android-native/app/src/main/java/in/recoveriq/app/`.
Port behaviour, API calls, filters, labels and business rules 1:1. Only the UI toolkit changes (Compose → SwiftUI).
The app is built UNSIGNED on a GitHub macOS runner (Xcode latest, XcodeGen) — nobody can compile locally, so
write conservative, explicitly-typed Swift that compiles first time.

## Platform & rules
* iOS **16.0+**, Swift 5 language mode, SwiftUI + `NavigationStack`, Swift Charts (`import Charts`), MapKit via
  `UIViewRepresentable` (MKMapView) — not the iOS 17 `Map` content builder.
* No third-party packages. No storyboards. Only Apple frameworks.
* Keep each file < ~700 lines; split big screens into several files/subviews (SwiftUI type-checker times out on
  huge `body`s — extract subviews/functions generously, avoid long chained ternaries inside `body`).
* Always annotate numeric literal types where mixing Int/Double. Use `String(format: "%.0f", x)` or the `inr()` helper.
* Concurrency: `async/await`, `Task { }`, `@MainActor` on view models / AppState. No Combine-heavy code.
* Syntax check every file you write: `/tmp/swift-6.0.3-RELEASE-ubuntu22.04/usr/bin/swift-frontend -parse FILE.swift`
  (parse only; type-checking UIKit/SwiftUI isn't possible on Linux — so re-read your code for type errors).

## Folder layout (`ios/RecoverIQ/`)
```
App/        RecoverIQApp.swift (@main, UIApplicationDelegateAdaptor), AppDelegate.swift, AppState.swift
Core/       API.swift (APIClient + all endpoints), Models.swift (+ Models*.swift), Session.swift (Keychain store),
            Realtime.swift (WebSocket data_changed), Updater.swift, Files.swift (save/share downloads)
Location/   LocationTracker.swift (background tracking — already written, keep), LocationOnce.swift (one-shot GPS)
UI/         Theme.swift, Components.swift, CaseCard.swift, Actions.swift, DateUtil.swift, DatePickerField.swift,
            Qr.swift, MapKitView.swift, GuidedTour.swift
Nav/        AppRoot.swift (role → nav entries, side menu / drawer), LoginView.swift, ViewPickerView.swift,
            ForcePasswordChangeView.swift
Features/   Fos/  Detail/  Caller/  TeamLead/  Common/  Admin/  Attendance/  Screens/  Ai/
```

## Naming — translate Kotlin names directly
* Kotlin data class `Case` → Swift `struct Case: Codable, Identifiable, Hashable`. **Property names identical to
  Kotlin** (camelCase); JSON keys via `CodingKeys` exactly as the Kotlin `@Json(name=...)` (else same name).
* Kotlin fields with a default (`val x: Double = 0.0`, `= false`, `= emptyList()`) stay **non-optional** in Swift:
  Models.swift provides `init(from:)` via the helper `KeyedDecodingContainer.d(_:_:default)` pattern, or the
  `@Default` property wrapper defined in Models.swift — porters just use them as non-optional.
  Nullable Kotlin fields (`String?`) stay optional.
* Kotlin `ApiService` function `fun myCases()` / Repository `suspend fun x()` → `API.shared.x(...) async throws -> T`
  with the same name and parameter names. Endpoints & query params exactly as ApiService.kt.
* Kotlin `vm: AuthViewModel` → `@EnvironmentObject var app: AppState` (has `user`, `config`, `logout()`,
  `switchView()`, `repo`-like helpers live on `API.shared`). `vm.repo.foo()` → `try await API.shared.foo()`.
* Compose → SwiftUI: `LazyColumn`→`ScrollView{LazyVStack}` or `List`; `FilterChip`→`Chip(label:selected:action:)`
  (Components.swift); `InfoCard`→`InfoCard{}`; `SectionTitle`→`SectionTitle("…")`; `AlertDialog`→`.sheet`/`.alert`;
  `rememberLiveKey()`→`.onReceive(Realtime.shared.changed)` reload; `LaunchedEffect(key)`→`.task(id: key)`;
  `Toast`→`app.toast("…")`.
* Colors: `Color.BrandBlue, Color.Muted, Color.Good, Color.Bad, Color.Warn, Color.Ink, Color.Surface` (Theme.swift)
  — same names as Theme.kt.
* Money: `inr(_ v: Double) -> String` ("₹1,23,456" Indian grouping). Dates: DateUtil.swift mirrors DateUtil.kt.
* Phone / WhatsApp / navigate / UPI: `Actions.call(phone)`, `Actions.whatsApp(phone, text:)`,
  `Actions.navigate(lat:lng:address:)` (Google Maps app if installed, else Apple Maps), `Actions.share(...)`.
* Downloads (Excel/PDF): `try await API.shared.download(path:query:) -> URL` (temp file) then `Files.share(url)`.
* Live refresh: `Realtime.shared.changed` is a `PassthroughSubject<Void,Never>` fired on WebSocket `data_changed`.

## Screen contract (exact SwiftUI names & inits — AppRoot already calls these)
| Swift view | Kotlin source | Group |
|---|---|---|
| `LoginView()`, `ViewPickerView(user:)`, `ForcePasswordChangeView(onChanged:)` | LoginScreen.kt, AppRoot.kt, ProfileScreen.kt | Core |
| `FieldAgentTrackingView()` (FOS home), `MyCasesView(onOpenCase:)`, `MyVisitsView(onOpenCase:)`, `JointCasesView(onOpenCase:)`, `FieldTrackingView()` | fos/*.kt | Fos |
| `CaseDetailView(caseId:)`, `LogVisitSheet(case:onDone:)`, `PaymentSheet(case:onDone:)`, `LogCallSheet(case:onDone:)` | detail/*.kt | Detail |
| `CallQueueView(onOpenCase:)`, `PtpTrackerView(onOpenCase:)`, `TeamLeadDashboardView(onOpenCase:)`, `PortfolioView(onOpenCase:)`, `MyPerformanceView()`, `CasesView(onOpenCase:)`, `TeamView()` | caller/, teamlead/, common/Portfolio, MyPerformance, SharedScreens, screens/TeamScreen | Caller/TL |
| `DashboardView()`, `AdminDashboardView()`, `LiveMapView()`, `MisView()` | admin/*.kt, common/MisScreen.kt | Admin |
| `AttendanceView()`, `LeaveView()`, `PayslipsView()`, `ProfileView()`, `ChangeRequestsView()` | attendance/, screens/ | HR |
| `RtsbView()`, `TodoView(onOpenCase:)`, `MonitorView()`, `LitigationView()`, `CommunicationView()`, `DevicesView()`, `ActivityView()`, `SecurityView()`, `AiAssistView()`, chat widget `ChatButton()` | common/CollabScreens.kt, screens/*, ai/ | Collab |

`onOpenCase: (Int) -> Void` pushes `CaseDetailView(caseId:)` (AppRoot handles it).
Each group owns ONLY its own files (`Features/<Group>/…`). Shared helpers missing from UI/ → add a private helper in
your own file instead of editing shared files (to avoid conflicts). Need a model/endpoint that's missing? Add it in
`Core/Models+<Group>.swift` / `Core/API+<Group>.swift` as an `extension` — never edit Models.swift/API.swift.
