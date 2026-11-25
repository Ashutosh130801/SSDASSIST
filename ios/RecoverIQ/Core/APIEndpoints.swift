import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// =====================================================================================
// All endpoints — port of ApiService.kt (Retrofit) + Repository.kt (wrappers).
//
// NAMING RULE: Kotlin `vm.repo.foo(a, b)` / `Api.service.foo(a, b)` → `try await API.shared.foo(a: a, b: b)`
// — same function name, Kotlin parameter names as argument labels, same defaults.
//  * Where ApiService and Repository have the SAME name + labels they are merged into one function with the
//    Repository behaviour (blank strings → nil, etc.).
//  * Retrofit `@Body body: X` → label `body:`. `Map<String, Any?>` → `[String: JSONValue]`
//    (nulls are dropped before sending, like Moshi). `Map<String, String?>` → `[String: String?]`.
//  * `ResponseBody` downloads → return a local temp file `URL` (then `Files.share(url)`).
//  * `case(id:)` is also available as `getCase(id:)`.
// =====================================================================================

extension API {

    // MARK: helpers

    /// Kotlin `ifBlank { null }`.
    static func nb(_ s: String?) -> String? {
        guard let s = s, !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return s
    }

    static func qs(_ i: Int?) -> String? { i.map { String($0) } }
    static func qs(_ b: Bool?) -> String? { b.map { $0 ? "true" : "false" } }
    static func qs(_ d: Double?) -> String? { d.map { String($0) } }

    /// Drop null values (Moshi doesn't serialise nulls).
    static func stripNulls(_ m: [String: JSONValue]) -> [String: JSONValue] {
        var o: [String: JSONValue] = [:]
        for (k, v) in m where !v.isNull { o[k] = v }
        return o
    }

    static func compact(_ m: [String: String?]) -> [String: String] {
        var o: [String: String] = [:]
        for (k, v) in m { if let v = v { o[k] = v } }
        return o
    }

    /// "Apple iPhone15,2" — the device label sent at login (Android: MANUFACTURER + MODEL).
    static var deviceLabel: String {
        var sys = utsname()
        uname(&sys)
        let machine: String = withUnsafeBytes(of: &sys.machine) { raw -> String in
            let bytes = raw.prefix { $0 != 0 }
            return String(decoding: bytes, as: UTF8.self)
        }
        return "Apple " + (machine.isEmpty ? "iPhone" : machine)
    }

    // MARK: - Auth / session (Repository)

    func login(body: LoginRequest) async throws -> Token {
        return try await post("api/auth/login-json", body: body)
    }

    /// Repository.login — normalises the email, sends device id + label, saves the session.
    func login(email: String, password: String, otp: String?) async throws -> Token {
        let req = LoginRequest(email: email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
                               password: password,
                               deviceId: Session.shared.deviceId,
                               deviceLabel: API.deviceLabel,
                               otp: API.nb(otp))
        let token: Token = try await login(body: req)
        Session.shared.save(token)
        return token
    }

    func me() async throws -> User { return try await get("api/auth/me") }

    func switchView(body: [String: String]) async throws -> Token {
        return try await post("api/auth/switch-view", body: body)
    }

    /// Repository.switchView — flips the active hat and saves the fresh token.
    func switchView(view: String) async throws -> Token {
        let t: Token = try await switchView(body: ["view": view])
        Session.shared.save(t)
        return t
    }

    func bootstrapToken() {}   // token is read from the Keychain on every request
    func currentUser() -> User? { Session.shared.user }
    func isLoggedIn() -> Bool { Session.shared.isLoggedIn }
    func logout() { Session.shared.clear() }
    func deviceId() -> String { Session.shared.deviceId }
    func onDuty() -> Bool { Session.shared.onDuty }
    func setOnDuty(v: Bool) { Session.shared.onDuty = v }

    private func myId() -> Int? { Session.shared.user?.id }

    /// GET /api/config — branding, UPI VPA, call scheme, catalog, etc.
    func config() async throws -> [String: JSONValue] { return try await get("api/config") }

    /// GET /api/services — on/off map of optional services (menus hide what's off).
    func services() async throws -> [[String: JSONValue]] { return try await get("api/services") }

    // MARK: - Tracking

    func ping(body: PingCreate) async throws -> PingOut { return try await post("api/tracking/ping", body: body) }
    func liveOfficers() async throws -> [OfficerLocation] { return try await get("api/tracking/live") }
    func myTodayRoute() async throws -> TodayRoute { return try await get("api/tracking/me/today") }

    func officerRoute(officerId: Int, date: String? = nil) async throws -> [PingOut] {
        return try await get("api/tracking/officer/\(officerId)/route", query: ["date": date])
    }

    func officerRoute(id: Int, date: String? = nil) async throws -> [PingOut] {
        return try await officerRoute(officerId: id, date: date)
    }

    // MARK: - Cases

    func cases(bank: String? = nil, product: String? = nil, branch: String? = nil, status: String? = nil,
               paidStatus: String? = nil, search: String? = nil, cycles: String? = nil, fosIds: String? = nil,
               callerIds: String? = nil, limit: Int = 500) async throws -> [Case] {
        let q: Query = ["bank": bank, "product": product, "branch": branch, "status": status,
                        "paid_status": paidStatus, "search": search, "cycles": cycles, "fos_ids": fosIds,
                        "caller_ids": callerIds, "limit": String(limit)]
        return try await get("api/cases", query: q)
    }

    /// Cases assigned to me (fos or caller) + cases escalated away from me (kept visible, locked).
    func myCases() async throws -> [Case] {
        let id = myId()
        let all: [Case] = try await cases(limit: 1000)
        return all.filter { c in
            c.assignedFosId == id || c.assignedCallerId == id ||
                (c.escalated == true && (c.escPrevFosId == id || c.escPrevCallerId == id))
        }
    }

    func allCases(bank: String? = nil, status: String? = nil, search: String? = nil) async throws -> [Case] {
        return try await cases(bank: bank, status: status, search: API.nb(search))
    }

    func portfolioCases(bank: String?, product: String?, branch: String?, paid: String?,
                        cycles: String?, fosIds: String?, callerIds: String?) async throws -> [Case] {
        return try await cases(bank: bank, product: product, branch: API.nb(branch), paidStatus: API.nb(paid),
                               cycles: API.nb(cycles), fosIds: API.nb(fosIds), callerIds: API.nb(callerIds), limit: 1000)
    }

    func jointMine() async throws -> [Case] { return try await get("api/cases/joint-mine") }
    func jointCases() async throws -> [Case] { return try await jointMine() }

    /// POST /api/cases/export → local .xlsx / .pdf file.
    func exportCases(body: CaseExportRequest) async throws -> URL {
        return try await download(path: "api/cases/export", postBody: body)
    }

    func exportCases(ids: [Int], fmt: String, title: String) async throws -> URL {
        return try await exportCases(body: CaseExportRequest(ids: ids, fmt: fmt, title: title))
    }

    func portfolioBanks(monthBucket: String? = nil) async throws -> [PortfolioBank] {
        return try await get("api/cases/portfolio-banks", query: ["month_bucket": API.nb(monthBucket)])
    }

    func productSummary(monthBucket: String? = nil) async throws -> [ProductSummary] {
        return try await get("api/cases/product-summary", query: ["month_bucket": API.nb(monthBucket)])
    }

    func mis(bank: String, product: String, monthBucket: String? = nil, area: String? = nil, branch: String? = nil,
             cycles: String? = nil, fosIds: String? = nil, callerIds: String? = nil,
             paid: String? = nil) async throws -> [String: JSONValue] {
        let q: Query = ["bank": bank, "product": product, "month_bucket": API.nb(monthBucket), "area": API.nb(area),
                        "branch": API.nb(branch), "cycles": API.nb(cycles), "fos_ids": API.nb(fosIds),
                        "caller_ids": API.nb(callerIds), "paid": API.nb(paid)]
        return try await get("api/mis", query: q)
    }

    func filterOptions(bank: String? = nil, product: String? = nil, branch: String? = nil) async throws -> FilterOptions {
        return try await get("api/cases/filter-options", query: ["bank": bank, "product": product, "branch": API.nb(branch)])
    }

    func areas(bank: String? = nil, product: String? = nil, branch: String? = nil) async throws -> [String] {
        return try await get("api/cases/areas", query: ["bank": bank, "product": product, "branch": API.nb(branch)])
    }

    func `case`(id: Int) async throws -> Case { return try await get("api/cases/\(id)") }
    func getCase(id: Int) async throws -> Case { return try await get("api/cases/\(id)") }

    func setReviewFlag(id: Int, body: [String: String?]) async throws -> Case {
        return try await post("api/cases/\(id)/review-flag", body: API.compact(body))
    }

    /// Personal colour highlight; nil/empty clears it.
    func setReviewFlag(id: Int, color: String?) async throws -> Case {
        return try await post("api/cases/\(id)/review-flag", body: ["color": color ?? ""])
    }

    func updateCase(id: Int, body: CaseUpdate) async throws -> Case {
        return try await patch("api/cases/\(id)", body: body)
    }

    func updateCase(id: Int, update: CaseUpdate) async throws -> Case {
        return try await updateCase(id: id, body: update)
    }

    func recordPayment(id: Int, body: PaymentRequest) async throws -> Case {
        return try await post("api/cases/\(id)/payment", body: body)
    }

    func recordPayment(id: Int, amount: Double, mode: String = "UPI", note: String? = nil,
                       normStab: String? = nil) async throws -> Case {
        return try await recordPayment(id: id, body: PaymentRequest(amount: amount, mode: mode, note: note, normStab: normStab))
    }

    func timeline(id: Int) async throws -> [TimelineEvent] { return try await get("api/cases/\(id)/timeline") }

    func contactUpdate(id: Int, body: [String: String?]) async throws -> Case {
        return try await patch("api/cases/\(id)/contact-update", body: API.compact(body))
    }

    /// Caller / head office records the customer's latest address / phone (notifies the FOS).
    func contactUpdate(caseId: Int, newAddress: String?, newPhone: String?) async throws -> Case {
        return try await contactUpdate(id: caseId, body: ["new_address": newAddress, "new_phone": newPhone])
    }

    // MARK: - Attendance

    func attMeToday() async throws -> MeToday { return try await get("api/attendance/me/today") }

    func attCheckin(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/attendance/checkin", body: API.stripNulls(body))
    }

    func attCheckin(lat: Double?, lng: Double?) async throws -> [String: JSONValue] {
        return try await attCheckin(body: ["lat": JSONValue(lat), "lng": JSONValue(lng), "platform": "ios",
                                           "device_id": .string(Session.shared.deviceId)])
    }

    /// Selfie check-in (multipart: file, lat, lng, platform, device_id).
    func attCheckinPhoto(bytes: Data, lat: Double?, lng: Double?) async throws -> [String: JSONValue] {
        var f = MultipartForm()
        f.addFile("file", filename: "checkin.jpg", mimeType: "image/jpeg", data: bytes)
        f.add("lat", lat.map { String($0) })
        f.add("lng", lng.map { String($0) })
        f.add("platform", "ios")
        f.add("device_id", Session.shared.deviceId)
        return try await multipart("api/attendance/checkin/photo", form: f)
    }

    func attCheckout(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/attendance/checkout", body: API.stripNulls(body))
    }

    func attCheckout(lat: Double?, lng: Double?) async throws -> [String: JSONValue] {
        return try await attCheckout(body: ["lat": JSONValue(lat), "lng": JSONValue(lng)])
    }

    func attOvertime() async throws -> [String: JSONValue] { return try await post("api/attendance/overtime") }

    func attHeartbeat(body: [String: JSONValue]) async throws -> HeartbeatResp {
        return try await post("api/attendance/heartbeat", body: API.stripNulls(body))
    }

    func attHeartbeat(active: Bool) async throws -> HeartbeatResp {
        return try await attHeartbeat(body: ["platform": "ios", "active": .bool(active)])
    }

    func attDay(date: String? = nil, role: String? = nil) async throws -> AttDay {
        return try await get("api/attendance/day", query: ["date": date, "role": API.nb(role)])
    }

    func attMonth(month: String? = nil, role: String? = nil, start: String? = nil, end: String? = nil) async throws -> [String: JSONValue] {
        return try await get("api/attendance/month", query: ["month": month, "role": API.nb(role), "start": start, "end": end])
    }

    func attDownload(month: String? = nil, role: String? = nil, start: String? = nil, end: String? = nil) async throws -> URL {
        return try await download(path: "api/attendance/download",
                                  query: ["month": month, "role": API.nb(role), "start": start, "end": end])
    }

    // MARK: - Performance / MIS

    func performance(empId: Int, role: String?, monthBucket: String = "current") async throws -> Performance {
        return try await get("api/mis/performance", query: ["emp_id": String(empId), "role": API.nb(role), "month_bucket": monthBucket])
    }

    func myPerformance(monthBucket: String = "current", bank: String? = nil, product: String? = nil) async throws -> Performance {
        return try await get("api/mis/my-performance",
                             query: ["month_bucket": monthBucket, "bank": API.nb(bank), "product": API.nb(product)])
    }

    func employeeTrends(userId: Int) async throws -> EmployeeTrends {
        return try await get("api/mis/employee-trends", query: ["user_id": String(userId)])
    }

    func myTrends() async throws -> EmployeeTrends {
        guard let id = myId() else { throw APIError.notSignedIn }
        return try await employeeTrends(userId: id)
    }

    // MARK: - Calls (telecaller)

    func logCall(body: CallCreate) async throws -> CallOut { return try await post("api/calls", body: body) }

    func callQueue(bank: String? = nil) async throws -> QueueResponse {
        return try await get("api/calls/queue", query: ["bank": bank])
    }

    func reminders() async throws -> RemindersResponse { return try await get("api/reminders") }

    func ptpTracker(bank: String? = nil, dateFrom: String? = nil, dateTo: String? = nil,
                    callerId: Int? = nil, fosId: Int? = nil) async throws -> PtpResponse {
        let q: Query = ["bank": bank, "date_from": API.nb(dateFrom), "date_to": API.nb(dateTo),
                        "caller_id": API.qs(callerId), "fos_id": API.qs(fosId)]
        return try await get("api/calls/ptp-tracker", query: q)
    }

    func callsForCase(id: Int) async throws -> [CallOut] { return try await get("api/calls/case/\(id)") }

    // MARK: - Visits (field)

    func visitsForCase(id: Int) async throws -> [VisitOut] { return try await get("api/visits/case/\(id)") }

    func officerDayVisits(id: Int, date: String? = nil) async throws -> OfficerDayVisits {
        return try await get("api/visits/officer/\(id)/day", query: ["date": date])
    }

    /// The signed-in FOS's own visits for a day (default today), each joined to its case.
    func myVisitsForDay(date: String? = nil) async throws -> OfficerDayVisits {
        guard let uid = myId() else { throw APIError.notSignedIn }
        return try await officerDayVisits(id: uid, date: date)
    }

    /// Field visit (multipart, optional visit photo + payment screenshot). Same parts as Android.
    func createVisit(caseId: Int, lat: Double?, lng: Double?, accuracy: Double?,
                     personMoved: Bool, paid: Bool, amount: Double,
                     disposition: String?, note: String?, photoJpeg: Data?, normStab: String? = nil,
                     ptpDate: String? = nil, paymentPhotoJpeg: Data? = nil,
                     addressSlot: String? = nil, gpsMock: Bool = false, gpsFixAgeS: Double? = nil,
                     gpsPincode: String? = nil, gpsAddress: String? = nil, gpsCity: String? = nil) async throws -> VisitOut {
        var f = MultipartForm()
        f.add("case_id", String(caseId))
        f.add("latitude", lat.map { String($0) })
        f.add("longitude", lng.map { String($0) })
        f.add("gps_accuracy", accuracy.map { String($0) })
        f.add("person_moved", personMoved ? "true" : "false")
        f.add("paid", paid ? "true" : "false")
        f.add("amount_collected", String(amount))
        f.add("norm_stab", normStab)
        f.add("disposition", disposition)
        f.add("ptp_date", ptpDate)
        f.add("note", note)
        f.addFile("photo", filename: "visit.jpg", mimeType: "image/jpeg", data: photoJpeg)
        f.addFile("payment_photo", filename: "payment.jpg", mimeType: "image/jpeg", data: paymentPhotoJpeg)
        f.add("address_slot", addressSlot)
        f.add("gps_mock", gpsMock ? "true" : "false")
        f.add("gps_fix_age_s", gpsFixAgeS.map { String($0) })
        f.add("gps_pincode", gpsPincode)
        f.add("gps_address", gpsAddress)
        f.add("gps_city", gpsCity)
        return try await multipart("api/visits", form: f)
    }

    // MARK: - Templates / messaging

    func templates() async throws -> [Template] { return try await get("api/templates") }
    func createTemplate(body: TemplateCreate) async throws -> Template { return try await post("api/templates", body: body) }
    func deleteTemplate(id: Int) async throws { try await void("DELETE", "api/templates/\(id)") }
    func logComm(body: CommLog) async throws { try await voidBody("POST", "api/templates/log", body: body) }

    func logComm(caseId: Int, channel: String, text: String?) async throws {
        try await logComm(body: CommLog(caseId: caseId, channel: channel, text: text))
    }

    // MARK: - Dashboard / activity

    func dashboard() async throws -> DashboardResponse { return try await get("api/analytics/dashboard") }

    func activity(kind: String = "all", limit: Int = 100) async throws -> [ActivityItem] {
        return try await get("api/analytics/activity", query: ["kind": kind, "limit": String(limit)])
    }

    // MARK: - Litigation

    func legalCases() async throws -> [Legal] { return try await get("api/legal") }
    func createLegal(body: LegalCreate) async throws -> Legal { return try await post("api/legal", body: body) }
    func deleteLegal(id: Int) async throws { try await void("DELETE", "api/legal/\(id)") }
    func legalInsights() async throws -> LegalInsights { return try await get("api/legal/insights") }

    // MARK: - Team lead / team

    func teamOverview(monthBucket: String = "current") async throws -> TeamOverview {
        return try await get("api/team/overview", query: ["month_bucket": monthBucket])
    }

    func myTeam() async throws -> [TeamMemberCard] { return try await get("api/team/my-team") }

    func users(role: String? = nil) async throws -> [User] { return try await get("api/users", query: ["role": role]) }
    func usersByRole(role: String) async throws -> [User] { return try await users(role: role) }
    func createUser(body: UserCreate) async throws -> User { return try await post("api/users", body: body) }
    func updateUser(id: Int, body: UserUpdate) async throws -> User { return try await patch("api/users/\(id)", body: body) }
    func deleteUser(id: Int) async throws { try await void("DELETE", "api/users/\(id)") }

    // MARK: - Leave

    func leaves(status: String? = nil, scope: String = "auto", leaveType: String? = nil, fromDate: String? = nil,
                toDate: String? = nil, q: String? = nil) async throws -> [Leave] {
        let query: Query = ["status": status, "scope": scope, "leave_type": leaveType,
                            "from_date": fromDate, "to_date": toDate, "q": q]
        return try await get("api/leaves", query: query)
    }

    func applyLeave(body: LeaveCreate) async throws -> Leave { return try await post("api/leaves", body: body) }
    func leaveBalance() async throws -> [LeaveBalance] { return try await get("api/leaves/balance") }

    func decideLeave(id: Int, decision: String) async throws -> Leave {
        return try await post("api/leaves/\(id)/\(decision)")
    }

    func decideLeave(id: Int, approve: Bool) async throws -> Leave {
        return try await decideLeave(id: id, decision: approve ? "approve" : "reject")
    }

    // MARK: - Devices

    func devices() async throws -> [Device] { return try await get("api/devices") }
    func approveDevice(id: Int) async throws { try await void("POST", "api/devices/\(id)/approve") }
    func revokeDevice(id: Int) async throws { try await void("POST", "api/devices/\(id)/revoke") }
    func deleteDevice(id: Int) async throws { try await void("DELETE", "api/devices/\(id)") }

    // MARK: - 2FA

    func twoFAStatus() async throws -> TwoFAStatus { return try await get("api/auth/2fa/status") }
    func twoFASetup() async throws -> TwoFASetup { return try await post("api/auth/2fa/setup") }
    func twoFAEnable(body: OtpBody) async throws -> TwoFAStatus { return try await post("api/auth/2fa/enable", body: body) }
    func twoFAEnable(otp: String) async throws -> TwoFAStatus { return try await twoFAEnable(body: OtpBody(otp: otp)) }
    func twoFADisable(body: OtpBody) async throws -> TwoFAStatus { return try await post("api/auth/2fa/disable", body: body) }
    func twoFADisable(otp: String) async throws -> TwoFAStatus { return try await twoFADisable(body: OtpBody(otp: otp)) }

    // MARK: - AI Assist

    func aiAssist(body: AIRequest) async throws -> AIResponse { return try await post("api/ai", body: body) }

    func aiAssist(prompt: String, context: String? = nil) async throws -> String {
        let r: AIResponse = try await aiAssist(body: AIRequest(prompt: prompt, context: context))
        return r.reply
    }

    // MARK: - My E-ID / profile

    func myProfile() async throws -> EmployeeProfile { return try await get("api/manpower/me") }

    func updateMyProfile(body: [String: String?]) async throws -> [String: JSONValue] {
        return try await patch("api/manpower/me", body: API.compact(body))
    }

    func updateMyProfile(patch: [String: String?]) async throws {
        let _: [String: JSONValue] = try await updateMyProfile(body: patch)
    }

    /// Upload/replace the signed-in employee's profile photo. Returns the new photo URL.
    func uploadProfilePhoto(bytes: Data, filename: String = "photo.jpg") async throws -> String? {
        var f = MultipartForm()
        f.addFile("file", filename: filename, mimeType: "image/jpeg", data: bytes)
        let r: [String: JSONValue] = try await multipart("api/manpower/me/photo", form: f)
        return r["photo_url"]?.string
    }

    func changePassword(body: ChangePasswordRequest) async throws -> Token {
        return try await post("api/auth/change-password", body: body)
    }

    /// Set a new password; refreshes the stored token + user so the app continues signed in.
    func changePassword(current: String, new: String) async throws -> Token {
        let t: Token = try await changePassword(body: ChangePasswordRequest(currentPassword: current, newPassword: new))
        Session.shared.save(t)
        return t
    }

    // MARK: - Profile change requests

    func myChangeFields() async throws -> [ChangeField] { return try await get("api/manpower/me/change-fields") }

    func submitChangeRequest(body: [String: String?]) async throws -> ProfileChangeRequest {
        return try await post("api/manpower/me/change-request", body: API.compact(body))
    }

    func submitChangeRequest(field: String, value: String, note: String?) async throws -> ProfileChangeRequest {
        return try await submitChangeRequest(body: ["field": field, "value": value, "note": note])
    }

    func myChangeRequests() async throws -> [ProfileChangeRequest] { return try await get("api/manpower/me/change-requests") }

    func changeRequests(status: String? = nil, q: String? = nil) async throws -> [ProfileChangeRequest] {
        return try await get("api/manpower/change-requests", query: ["status": status, "q": q])
    }

    func decideChangeRequest(id: Int, decision: String, body: [String: String?]) async throws -> ProfileChangeRequest {
        return try await post("api/manpower/change-requests/\(id)/\(decision)", body: API.compact(body))
    }

    func decideChangeRequest(id: Int, approve: Bool, reviewNote: String?) async throws -> ProfileChangeRequest {
        return try await decideChangeRequest(id: id, decision: approve ? "approve" : "reject", body: ["review_note": reviewNote])
    }

    // MARK: - Notifications (bell)

    func notifications(limit: Int = 30) async throws -> NotificationList {
        return try await get("api/notifications", query: ["limit": String(limit)])
    }

    func markNotificationRead(id: Int) async throws { try await void("POST", "api/notifications/\(id)/read") }
    func markAllNotificationsRead() async throws { try await void("POST", "api/notifications/read-all") }

    // MARK: - Collaboration / ops (RTSB, To-Do, Live Monitor, Liner, Chat)

    func rtsb(monthBucket: String?, role: String?) async throws -> [String: JSONValue] {
        return try await get("api/mis/rtsb", query: ["month_bucket": API.nb(monthBucket), "role": API.nb(role)])
    }

    func todoMe() async throws -> [String: JSONValue] { return try await get("api/todo/me") }
    func monitorLive() async throws -> [String: JSONValue] { return try await get("api/monitor/live") }

    func liner(fosId: Int? = nil) async throws -> [String: JSONValue] {
        return try await get("api/liner", query: ["fos_id": API.qs(fosId)])
    }

    func chatContacts() async throws -> [String: JSONValue] { return try await get("api/chat/contacts") }

    /// Repository semantics: `office` false → param omitted.
    func chatThread(withId: Int?, office: Bool) async throws -> [String: JSONValue] {
        return try await get("api/chat/thread", query: ["with_id": API.qs(withId), "office": office ? "true" : nil])
    }

    func chatSend(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/chat/send", body: API.stripNulls(body))
    }

    func chatRequest(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/chat/request", body: API.stripNulls(body))
    }

    func chatRequest(toId: Int) async throws -> [String: JSONValue] {
        return try await chatRequest(body: ["to_id": .int(toId)])
    }

    func chatRequests() async throws -> [String: JSONValue] { return try await get("api/chat/requests") }

    func chatRequestDecide(id: Int, body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/chat/request/\(id)/decide", body: API.stripNulls(body))
    }

    func chatBroadcast(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/chat/broadcast", body: API.stripNulls(body))
    }

    func chatBroadcast(toIds: [Int], body: String) async throws -> [String: JSONValue] {
        let payload: [String: JSONValue] = ["to_ids": JSONValue(toIds), "body": .string(body)]
        return try await chatBroadcast(body: payload)
    }

    func chatCallback(body: [String: JSONValue]) async throws -> [String: JSONValue] {
        return try await post("api/chat/callback", body: API.stripNulls(body))
    }

    func chatCallback(caseId: Int, note: String?) async throws -> [String: JSONValue] {
        return try await chatCallback(body: ["case_id": .int(caseId), "note": JSONValue(note)])
    }

    /// Repository semantics: unread count as Int (0 on missing).
    func chatUnread() async throws -> Int {
        let m: [String: JSONValue] = try await get("api/chat/unread")
        return m["unread"]?.int ?? 0
    }

    // MARK: - Payroll self-service

    func myPayslips() async throws -> [[String: JSONValue]] { return try await get("api/payroll/my") }
    func myPayslipPdf(id: Int) async throws -> URL { return try await download(path: "api/payroll/my/\(id).pdf") }
    func myTax() async throws -> [String: JSONValue] { return try await get("api/payroll/my/tax") }

    func myForm16(fy: String?) async throws -> URL {
        return try await download(path: "api/payroll/my/form16.pdf", query: ["fy": fy])
    }
}
