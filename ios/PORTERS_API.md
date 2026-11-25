# Foundation API available to screen porters (already built — read the source if unsure)

Read `ios/NATIVE_PORT.md` first. Foundation code lives in `ios/RecoverIQ/{App,Core,UI,Nav,Location}` — DO NOT edit those
files; add `Core/API+<Group>.swift` / `Core/Models+<Group>.swift` extensions or private helpers in your own files.

**AppState** (`@EnvironmentObject var app: AppState`, @MainActor): `user: User?`, `isLoggedIn`, `toast(_ msg)`,
`switchView(_:)`, `refreshUser()`, `setUser(_:)`, `config` + `configString(_:)`, `upiVpa`, `upiPayeeName`, `callScheme`,
`brandName`, `aiEnabled`, `services` + `isServiceOn(_:)`, `payslipsOn`, `logout()`. Non-View code: `showToast("…")`.

**API** — `try await API.shared.<kotlinName>(<kotlinParamLabels>…)`; `@Body` → `body:`; Map<String,Any?> → `[String: JSONValue]`;
downloads return a temp-file `URL` → `Files.share(url)`. Examples: `myCases() -> [Case]`,
`createVisit(caseId:lat:lng:accuracy:personMoved:paid:amount:disposition:note:photoJpeg:normStab:ptpDate:paymentPhotoJpeg:addressSlot:gpsMock:gpsFixAgeS:gpsPincode:gpsAddress:gpsCity:) -> VisitOut`,
`ptpTracker(bank:dateFrom:dateTo:callerId:fosId:) -> PtpResponse`,
`mis(bank:product:monthBucket:area:branch:cycles:fosIds:callerIds:paid:) -> [String: JSONValue]`,
`attDownload(month:role:start:end:) -> URL`, `exportCases(ids:fmt:title:) -> URL`, `getCase(id:)`.
All endpoints are in `Core/APIEndpoints.swift` (grep it). Generic verbs for new endpoints: `get/post/put/patch/delete/void/voidBody`,
`multipart(_:form: MultipartForm)`, `download(path:query:method:body:)`; query is `[String: String?]` (nil skipped).
`APIError` (`statusCode`, `detail`, `localizedDescription` = FastAPI detail). `JSONValue` enum in Core/JSONValue.swift.

**Models**: all Kotlin data classes ported in `Core/Models*.swift` with the SAME property names; Kotlin-defaulted fields are
non-optional, nullable ones optional; memberwise inits with Kotlin defaults (e.g. `CallCreate(caseId: 1, disposition: "PTP")`).

**UI components** (UI/Components.swift etc.): `inr(_:)`, `pct(_:)`, `LogoLoader(size:)`,
`AsyncContent(key:live:load:) { value, reload in … }`, `SectionTitle("…")`, `InfoCard(spacing:padding:) { }`,
`TrendStrip(trends:title:)`, `DataList(items:emptyText:) { row }`, `StatusChip(status:)`, `PaidTag(paidStatus:)`,
`TouchTag(text:color:)`, `PersonChip(text:){}`, `Chip(label:selected:action:)`, `StatTile(label:value:color:sub:)`,
`EmptyState(text:systemImage:)`, `ErrorView(message:retry:)`, `PrimaryButton(title:busy:enabled:color:action:)`,
`FlowLayout(spacing:lineSpacing:)` (FlowRow), `ToastBanner`, `LabeledField(label:){}` (Nav/LoginView.swift),
fonts `.titleMedium/.bodySmall/.labelSmall…`, colors `Color.BrandBlue/.Muted/.Good/.Bad/.Warn/.Ink/.TextDark/.Surface/.CardWhite/.GlassStroke`,
`Color(argb: 0xFF2563EB)`. `reviewColorOf(_:)`, `REVIEW_COLOR_NAMES`.
`CaseCard(case:onClick:showQuickActions:subtitle:onOpenPerf:)`. `DatePickerField`, `QrImage` (UI/Qr.swift), `GuidedTour`.

**Actions**: `call/dial(_:)`, `dialViaZoiper(_:scheme:)`, `whatsApp(_:text:)`, `navigate(lat:lng:address:)`, `mapsSearch(_:)`,
`shareVisit(message:photoJpeg:paymentPhotoJpeg:)`, `shareVisitToSelf(selfPhone:message:photoJpeg:)`, `share(items:)`, `share(text:)`,
`upiLink(vpa:payee:amount:note:)`, `openUpi(...)`, `open(_:)` (check UI/Actions.swift for the exact namespace).

**Map**: `MapKitView(markers: [RIQMapMarker], lines: [RIQMapLine], showsUserLocation:, fitKey: AnyHashable?, centerOn:, centerZoomMeters:, onMarkerTap:)`;
`RIQMapMarker(id:latitude:longitude:title:subtitle:color: UIColor, style: .pin/.dot/.liveDot/.arrow(bearing:), alpha:, tag:)`;
`RIQMapLine(id:coordinates:color:width:arrows:dashed:)`; `bearingDeg(_:_:)`.

**Location**: `try await LocationOnce.current(timeout:desiredAccuracy:maxAge:) -> GPSFix(latitude, longitude, accuracy, isMock, ageSeconds)`,
`await LocationOnce.reverseGeocode(fix) -> GeoAddress?(pincode,address,city)`. `LocationTracker.shared`: `start() stop() running permission lastFix lastError requestPermission() openSettings()`.
**Files**: `Files.share(url)`, `Files.share([urls])`, `Files.saveTemp(_:name:)`, `Files.saveToDocuments(_:)`, `Files.topViewController()`.
**Realtime**: `.onReceive(Realtime.shared.changed) { _ in reload() }`; also `openCase`, `notification`, `broadcast` publishers.
