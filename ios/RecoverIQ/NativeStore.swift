import Foundation
import Security

/// Small persistent store shared by the web bridge and the background tracker.
/// The sign-in token lives in the Keychain (readable after the first unlock, so a background
/// relaunch on a locked phone can still post locations); everything else in UserDefaults.
enum NativeStore {
    private static let defaults = UserDefaults.standard
    static let defaultBase = "https://recoveriq.ssdenterprises.org.in/"

    /// The RecoverIQ server this build opens (set at build time from the APP_URL secret).
    static var baseURL: URL {
        var s = (Bundle.main.object(forInfoDictionaryKey: "RIQBaseURL") as? String) ?? ""
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.isEmpty || s.contains("$(") { s = defaultBase }
        if !s.hasSuffix("/") { s += "/" }
        return URL(string: s) ?? URL(string: defaultBase)!
    }

    static var token: String {
        get { Keychain.get("riq.token") ?? defaults.string(forKey: "riq.token.fallback") ?? "" }
        set {
            if Keychain.set(newValue, for: "riq.token") {
                defaults.removeObject(forKey: "riq.token.fallback")
            } else {
                // Keychain unavailable (unusual signing) → fall back so tracking still works.
                defaults.set(newValue.isEmpty ? nil : newValue, forKey: "riq.token.fallback")
            }
        }
    }

    /// The same device id the web app uses (ssd_device) — check-in pins tracking to it.
    static var deviceId: String {
        get { defaults.string(forKey: "riq.device") ?? "" }
        set { if !newValue.isEmpty { defaults.set(newValue, forKey: "riq.device") } }
    }

    static var userJSON: String {
        get { defaults.string(forKey: "riq.user") ?? "" }
        set { defaults.set(newValue, forKey: "riq.user") }
    }

    static var trackingEnabled: Bool {
        get { defaults.bool(forKey: "riq.tracking") }
        set { defaults.set(newValue, forKey: "riq.tracking") }
    }

    static var userRole: String {
        guard let d = userJSON.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return "" }
        return (obj["role"] as? String) ?? ""
    }

    static func clearSession() {
        token = ""
        userJSON = ""
        trackingEnabled = false
    }
}

enum Keychain {
    private static let service = "in.recoveriq.app"

    private static func base(_ key: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
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
}

enum AppInfo {
    static var version: String { (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "1.0" }
    static var build: Int { Int((Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String) ?? "0") ?? 0 }
}
