import Foundation
#if canImport(Security)
import Security
#endif

/// Persists the JWT + the signed-in user across launches (port of data/Session.kt, replaces the
/// hybrid app's NativeStore). The token lives in the Keychain (readable after first unlock, so a
/// silent background relaunch on a locked phone can still post locations); the rest in UserDefaults.
/// Thread-safe enough for our use (UserDefaults/Keychain are themselves thread-safe).
final class Session {
    static let shared = Session()

    private let defaults = UserDefaults.standard
    static let defaultBase = "https://recoveriq.ssdenterprises.org.in/"

    private let kToken = "riq.token"
    private let kTokenFallback = "riq.token.fallback"
    private let kUser = "riq.user"
    private let kDevice = "riq.device"
    private let kTracking = "riq.tracking"

    private init() {}

    // MARK: - Server

    /// The RecoverIQ server this build talks to (Info.plist RIQBaseURL, set at build time). Always ends in "/".
    static var baseURL: URL {
        var s = (Bundle.main.object(forInfoDictionaryKey: "RIQBaseURL") as? String) ?? ""
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty || s.contains("$(") { s = defaultBase }
        if !s.hasSuffix("/") { s += "/" }
        return URL(string: s) ?? URL(string: defaultBase)!
    }

    /// Base URL string without the trailing slash (for building absolute photo URLs: base + "/uploads/…").
    static var baseString: String {
        var s = baseURL.absoluteString
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// Make a server-relative ref ("/uploads/x.jpg") absolute; http(s) refs are returned unchanged.
    static func absoluteURL(_ ref: String?) -> URL? {
        guard let r = ref?.trimmingCharacters(in: .whitespaces), !r.isEmpty else { return nil }
        if r.hasPrefix("http://") || r.hasPrefix("https://") { return URL(string: r) }
        return URL(string: baseString + (r.hasPrefix("/") ? r : "/" + r))
    }

    // MARK: - Token

    var token: String? {
        get {
            let k = Keychain.get(kToken) ?? defaults.string(forKey: kTokenFallback)
            if let k = k, !k.isEmpty { return k }
            return nil
        }
        set {
            let v = newValue ?? ""
            if Keychain.set(v, for: kToken) {
                defaults.removeObject(forKey: kTokenFallback)
            } else {
                // Keychain unavailable (unusual signing) → fall back so the app still works.
                if v.isEmpty { defaults.removeObject(forKey: kTokenFallback) } else { defaults.set(v, forKey: kTokenFallback) }
            }
        }
    }

    var isLoggedIn: Bool { !(token ?? "").isEmpty }

    // MARK: - User

    var user: User? {
        get {
            guard let s = defaults.string(forKey: kUser), let d = s.data(using: .utf8) else { return nil }
            return try? JSONDecoder().decode(User.self, from: d)
        }
        set {
            if let u = newValue, let d = try? JSONEncoder().encode(u), let s = String(data: d, encoding: .utf8) {
                defaults.set(s, forKey: kUser)
            } else {
                defaults.removeObject(forKey: kUser)
            }
        }
    }

    /// Role of the saved user ("" when none) — used by the background tracker before any UI exists.
    var userRole: String { user?.role ?? "" }

    func save(_ token: Token) {
        self.token = token.accessToken
        self.user = token.user
    }

    /// Sign-out: drop token + user and switch duty/tracking off (device id is kept).
    func clear() {
        token = nil
        user = nil
        onDuty = false
    }

    // MARK: - Device id

    /// A stable per-install device id for the login device-gate and check-in/tracking pinning.
    /// Kept in the Keychain too, so it survives a reinstall (a re-approval is then not needed).
    var deviceId: String {
        if let d = defaults.string(forKey: kDevice), !d.isEmpty { return d }
        if let k = Keychain.get(kDevice), !k.isEmpty {
            defaults.set(k, forKey: kDevice)
            return k
        }
        let raw = UUID().uuidString.lowercased()
        let fresh = "ios-" + String(raw.prefix(12))
        defaults.set(fresh, forKey: kDevice)
        _ = Keychain.set(fresh, for: kDevice)
        return fresh
    }

    // MARK: - On duty / tracking

    /// Persisted "on duty" flag (Android Session.onDuty). The background LocationTracker uses the same
    /// flag as its "tracking enabled" switch, so the toggle reflects the real state everywhere.
    var onDuty: Bool {
        get { defaults.bool(forKey: kTracking) }
        set { defaults.set(newValue, forKey: kTracking) }
    }

    var trackingEnabled: Bool {
        get { onDuty }
        set { onDuty = newValue }
    }
}

/// Minimal Keychain wrapper (generic passwords, accessible after first unlock).
enum Keychain {
    private static let service = "in.recoveriq.app"

    #if canImport(Security)
    private static func base(_ key: String) -> [String: Any] {
        return [kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: key]
    }

    @discardableResult
    static func set(_ value: String, for key: String) -> Bool {
        let q = base(key)
        let del = SecItemDelete(q as CFDictionary)
        if value.isEmpty { return del == errSecSuccess || del == errSecItemNotFound }
        var add = q
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }

    static func get(_ key: String) -> String? {
        var q = base(key)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data, let s = String(data: data, encoding: .utf8), !s.isEmpty else { return nil }
        return s
    }
    #else
    // Non-Apple platforms (Linux type-check only): plain UserDefaults.
    @discardableResult
    static func set(_ value: String, for key: String) -> Bool {
        UserDefaults.standard.set(value.isEmpty ? nil : value, forKey: service + "." + key)
        return true
    }

    static func get(_ key: String) -> String? {
        let s = UserDefaults.standard.string(forKey: service + "." + key)
        return (s?.isEmpty ?? true) ? nil : s
    }
    #endif
}

/// Bundle version info (used by the updater and the User-Agent).
enum AppInfo {
    static var version: String { (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "1.0" }
    static var build: Int { Int((Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String) ?? "0") ?? 0 }
}
