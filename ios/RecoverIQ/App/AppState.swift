import SwiftUI
import Combine

/// Signed-in state (Kotlin AuthState).
enum AuthState: Equatable {
    case loading
    case loggedOut
    case loggedIn(User)
}

/// App-wide state — port of ui/AuthViewModel.kt. Injected as `@EnvironmentObject var app: AppState`.
///
///  * `state` / `user` / `isLoggedIn`
///  * `login(email:password:otp:)` (2FA → `needsOtp`), `error`, `busy`
///  * `pickView` + `showViewPicker()` + `switchView(_:)` for dual-role users
///  * `logout()` (stops tracking, disconnects realtime, clears Session)
///  * `toast(_:)` / `toastMessage`
///  * `mustChangePassword` (first login with the starter password) + `passwordChanged(_:)`
///  * `config` (/api/config) + `services` (/api/services on/off) + `isServiceOn(_:)`, `payslipsOn`
///  * `setUser(_:)` / `refreshUser()` to keep the cached user fresh after profile edits.
@MainActor
final class AppState: ObservableObject {
    @Published private(set) var state: AuthState = .loading
    @Published var error: String? = nil
    @Published var busy: Bool = false
    /// True when the server said "2FA_REQUIRED" — LoginView shows the OTP field.
    @Published var needsOtp: Bool = false
    /// True right after a dual-role user logs in (or taps Switch view): show the hat picker.
    @Published var pickView: Bool = false
    /// First login with the shared starter password: force a change before anything else.
    @Published var mustChangePassword: Bool = false
    @Published var toastMessage: String? = nil
    @Published var config: [String: JSONValue] = [:]
    @Published var services: [String: Bool] = [:]
    /// "My Payslips" nav only when the salary section answers (it returns 423 while locked).
    @Published var payslipsOn: Bool = false

    private var observers: [NSObjectProtocol] = []
    private var toastTask: Task<Void, Never>? = nil

    init() {
        if let u = Session.shared.user, Session.shared.isLoggedIn {
            state = .loggedIn(u)
            mustChangePassword = u.mustChangePassword
            afterSignIn(u)
        } else {
            state = .loggedOut
        }
        let nc = NotificationCenter.default
        // Server rejected the token (e.g. field officer's 7pm expiry) → drop to login.
        observers.append(nc.addObserver(forName: .riqForceLogout, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in
                guard let self = self else { return }
                if case .loggedIn = self.state {
                    self.logout()
                    self.toast("Session ended — please sign in again.")
                }
            }
        })
        observers.append(nc.addObserver(forName: .riqToast, object: nil, queue: .main) { [weak self] note in
            let msg = (note.userInfo?["message"] as? String) ?? ""
            Task { @MainActor in self?.toast(msg) }
        })
    }

    deinit {
        for o in observers { NotificationCenter.default.removeObserver(o) }
    }

    // MARK: - Derived

    var user: User? {
        if case .loggedIn(let u) = state { return u }
        return nil
    }

    var isLoggedIn: Bool { user != nil }

    // MARK: - Login

    func login(email: String, password: String, otp: String?) {
        if busy { return }
        busy = true
        error = nil
        Task { @MainActor in
            defer { self.busy = false }
            do {
                let token = try await API.shared.login(email: email, password: password, otp: otp)
                self.needsOtp = false
                self.pickView = token.user.availableViews.count > 1   // dual role → ask which hat
                self.mustChangePassword = token.user.mustChangePassword
                self.state = .loggedIn(token.user)
                self.afterSignIn(token.user)
            } catch let e as APIError {
                self.error = AppState.loginMessage(e)
                if e.body.contains("2FA_REQUIRED") { self.needsOtp = true }
            } catch {
                self.error = "Network error (\(type(of: error))). Check your connection."
            }
        }
    }

    static func loginMessage(_ e: APIError) -> String {
        switch e {
        case .http(let code, let detail, let body):
            if body.contains("2FA_REQUIRED") { return "Enter your 6-digit authenticator code." }
            if code == 429 { return "Too many attempts — try again in a few minutes." }
            if code == 403 { return detail ?? "This device is awaiting admin approval." }
            if code == 401 { return "Invalid email or password." }
            if code >= 500 { return "Server error — the backend is down or out of disk space. Contact your admin." }
            return detail ?? "Sign-in failed (\(code))."
        default:
            return e.localizedDescription
        }
    }

    // MARK: - Views (dual role)

    func showViewPicker() { pickView = true }

    /// Switch the active hat (caller/FOS ↔ team lead) and re-render as that view.
    func switchView(_ view: String) {
        Task { @MainActor in
            do {
                let t = try await API.shared.switchView(view: view)
                self.pickView = false
                self.state = .loggedIn(t.user)
                self.afterSignIn(t.user)
            } catch {
                self.error = "Could not switch view."
                self.toast("Could not switch view.")
            }
        }
    }

    // MARK: - Logout

    func logout() {
        LocationTracker.shared.stop()            // stop background location if on duty
        Realtime.shared.disconnect()
        API.shared.logout()                      // Session.clear()
        needsOtp = false
        pickView = false
        mustChangePassword = false
        payslipsOn = false
        services = [:]
        state = .loggedOut
    }

    // MARK: - Toast

    func toast(_ message: String) {
        guard !message.isEmpty else { return }
        toastMessage = message
        toastTask?.cancel()
        toastTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 2_600_000_000)
            if Task.isCancelled { return }
            self?.toastMessage = nil
        }
    }

    // MARK: - User refresh

    /// Replace the cached user (also persisted to Session).
    func setUser(_ u: User) {
        Session.shared.user = u
        if case .loggedIn = state { state = .loggedIn(u) }
    }

    func refreshUser() async {
        if let u = try? await API.shared.me() { setUser(u) }
    }

    /// After ForcePasswordChangeView / Security change-password succeeded.
    func passwordChanged(_ token: Token) {
        mustChangePassword = false
        setUser(token.user)
    }

    // MARK: - Config / services

    func loadConfig() async {
        if let c = try? await API.shared.config() { config = c }
        if let list = try? await API.shared.services() {
            var m: [String: Bool] = [:]
            for s in list {
                if let k = s["key"]?.string { m[k] = s["enabled"]?.bool ?? true }
            }
            services = m
        }
    }

    func checkPayslips() async {
        payslipsOn = (try? await API.shared.myPayslips()) != nil
    }

    /// Unknown services count as ON (the server gates them anyway).
    func isServiceOn(_ key: String) -> Bool { services[key] ?? true }

    func configString(_ key: String) -> String? {
        let s = config[key]?.string ?? ""
        return s.isEmpty ? nil : s
    }

    var upiVpa: String? { configString("upi_vpa") }
    var upiPayeeName: String? { configString("upi_payee_name") }
    var callScheme: String? { configString("call_scheme") }
    var brandName: String { configString("brand_name") ?? "RecoverIQ" }
    var aiEnabled: Bool { config["ai_enabled"]?.bool ?? true }

    // MARK: - Private

    /// Kick off per-session side work: config, payslips check, FOS location permission / resume.
    private func afterSignIn(_ u: User) {
        Task { @MainActor in
            await self.loadConfig()
            await self.checkPayslips()
        }
        let field = u.role == "fos" || u.activeView == "fos"
        if field {
            // Like MainActivity.ensureLocationPermissions(): ask early; tracking itself follows the On Duty toggle.
            LocationTracker.shared.requestPermission()
            LocationTracker.shared.resumeIfEnabled()
        } else if LocationTracker.shared.running && !u.alsoFieldAgent {
            LocationTracker.shared.stop()
        }
    }
}
