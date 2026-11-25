import CoreLocation
import UIKit
import UserNotifications
import Combine

/// Always-on FOS location tracking — the iOS counterpart of the Android LocationService
/// (location/LocationService.kt + Tracking.start/stop).
///
/// Runs in native code, so it keeps reporting while the app is in the background or the phone is locked:
///  • standard GPS updates with `allowsBackgroundLocationUpdates` (blue location pill),
///  • plus significant-location-change monitoring, which makes iOS RELAUNCH the app after a restart / when
///    it was closed, so tracking resumes by itself after ~500 m of movement (AppDelegate.resumeIfEnabled()).
/// Each fix is posted to /api/tracking/ping with the Session token + device id.
///
/// Screens: `LocationTracker.shared.start()` (On Duty ON), `.stop()` (OFF), observe `running`,
/// `permission`, `lastFix`, `lastError` (it's an ObservableObject — use `@ObservedObject var tracker = LocationTracker.shared`).
final class LocationTracker: NSObject, ObservableObject, CLLocationManagerDelegate {
    static let shared = LocationTracker()

    private let manager = CLLocationManager()
    @Published private(set) var running = false
    @Published private(set) var lastFix: CLLocation?
    @Published private(set) var lastError: String?
    @Published private(set) var permission: String = "unknown"
    @Published private(set) var lastSentAt = Date.distantPast
    private var lastSentLoc: CLLocation?
    private var inFlight = false

    // Same cadence as Android: keep-alive every 20 s when standing still, while MOVING send as
    // often as every 3 s once the officer has moved 20 m (route quality without DB spam).
    private let heartbeat: TimeInterval = 20
    private let minGap: TimeInterval = 3
    private let minMove: CLLocationDistance = 20

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
        manager.activityType = .otherNavigation
        manager.pausesLocationUpdatesAutomatically = false
        permission = permissionName()
    }

    private var authStatus: CLAuthorizationStatus {
        if #available(iOS 14.0, *) { return manager.authorizationStatus }
        return CLLocationManager.authorizationStatus()
    }

    private var hasBackgroundMode: Bool {
        let modes = Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") as? [String] ?? []
        return modes.contains("location")
    }

    /// Persisted on-duty flag (shared with Session.onDuty).
    var enabled: Bool { Session.shared.trackingEnabled }

    /// "always" | "when_in_use" | "denied" | "restricted" | "not_determined" | "unknown"
    func permissionName() -> String {
        switch authStatus {
        case .authorizedAlways: return "always"
        case .authorizedWhenInUse: return "when_in_use"
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "not_determined"
        @unknown default: return "unknown"
        }
    }

    var hasAlwaysPermission: Bool { authStatus == .authorizedAlways }

    // MARK: - Control

    /// Start (or keep) tracking. Asks for permission the first time: "While Using" first, then iOS
    /// offers "Change to Always Allow", which is what lets tracking run with the screen locked.
    func start() {
        Session.shared.trackingEnabled = true
        requestNotificationPermission()
        switch authStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse:
            begin()
            manager.requestAlwaysAuthorization()
        case .authorizedAlways:
            begin()
        default:
            lastError = "Location permission is off"
        }
    }

    func stop(keepEnabled: Bool = false) {
        if !keepEnabled { Session.shared.trackingEnabled = false }
        running = false
        manager.stopUpdatingLocation()
        manager.stopMonitoringSignificantLocationChanges()
        if hasBackgroundMode { manager.allowsBackgroundLocationUpdates = false }
    }

    /// Called at every launch (also silent background relaunches) and when the app becomes active.
    func resumeIfEnabled() {
        guard Session.shared.trackingEnabled, Session.shared.isLoggedIn else { return }
        let role = Session.shared.userRole
        let view = Session.shared.user?.activeView ?? ""
        guard role.isEmpty || role == "fos" || view == "fos" || (Session.shared.user?.alsoFieldAgent ?? false) else { return }
        if !running { start() }
    }

    /// Ask for "Always" permission up-front (Android ensureLocationPermissions equivalent).
    func requestPermission() {
        switch authStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse: manager.requestAlwaysAuthorization()
        default: break
        }
    }

    /// Open the app's page in Settings (to switch location to "Always").
    func openSettings() {
        if let u = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(u) }
    }

    private func begin() {
        guard !running else { return }
        running = true
        if hasBackgroundMode { manager.allowsBackgroundLocationUpdates = true }
        manager.showsBackgroundLocationIndicator = true
        manager.startUpdatingLocation()
        if CLLocationManager.significantLocationChangeMonitoringAvailable() {
            manager.startMonitoringSignificantLocationChanges()
        }
    }

    /// Diagnostic snapshot (tracking banner / settings screen).
    func status() -> [String: Any] {
        var out: [String: Any] = ["running": running, "enabled": Session.shared.trackingEnabled, "permission": permissionName(),
                                  "platform": "ios", "version": AppInfo.version, "build": AppInfo.build]
        if let f = lastFix {
            out["last_fix"] = ["lat": f.coordinate.latitude, "lng": f.coordinate.longitude,
                               "accuracy": f.horizontalAccuracy, "at": f.timestamp.timeIntervalSince1970 * 1000]
        }
        if let e = lastError { out["error"] = e }
        return out
    }

    // MARK: - CLLocationManagerDelegate

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authChanged()
    }

    // iOS 13 path
    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        if #available(iOS 14.0, *) { return }
        authChanged()
    }

    private func authChanged() {
        permission = permissionName()
        guard Session.shared.trackingEnabled else { return }
        switch authStatus {
        case .authorizedWhenInUse:
            begin()
            manager.requestAlwaysAuthorization()
        case .authorizedAlways:
            begin()
        case .denied, .restricted:
            lastError = "Location permission is off"
            stop(keepEnabled: true)
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last, loc.horizontalAccuracy >= 0 else { return }
        lastFix = loc
        guard Session.shared.trackingEnabled else { return }
        let now = Date()
        let since = now.timeIntervalSince(lastSentAt)
        let moved = lastSentLoc.map { loc.distance(from: $0) } ?? .greatestFiniteMagnitude
        guard since >= heartbeat || (since >= minGap && moved >= minMove) else { return }
        post(loc)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if let e = error as? CLError, e.code == .locationUnknown { return }   // transient
        lastError = error.localizedDescription
    }

    // MARK: - Posting

    private func post(_ loc: CLLocation) {
        guard let token = Session.shared.token, !token.isEmpty, !inFlight else { return }
        inFlight = true
        lastSentAt = Date()
        lastSentLoc = loc

        var body: [String: Any] = ["latitude": loc.coordinate.latitude, "longitude": loc.coordinate.longitude,
                                   "accuracy": loc.horizontalAccuracy]
        if loc.speed >= 0 { body["speed"] = loc.speed }
        body["device_id"] = Session.shared.deviceId

        var req = URLRequest(url: Session.baseURL.appendingPathComponent("api/tracking/ping"))
        req.httpMethod = "POST"
        req.timeoutInterval = 20
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        req.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")
        req.setValue("RecoverIQ-iOS/" + AppInfo.version, forHTTPHeaderField: "User-Agent")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        // Finish the request even if iOS is about to suspend the app.
        var bgTask: UIBackgroundTaskIdentifier = .invalid
        bgTask = UIApplication.shared.beginBackgroundTask(withName: "riq.ping") {
            UIApplication.shared.endBackgroundTask(bgTask)
            bgTask = .invalid
        }
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, err in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.inFlight = false
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if code == 401 {
                    // Session ended (logout elsewhere / token expired) — stop using GPS and battery.
                    self.lastError = "Signed out — open RecoverIQ and sign in again"
                    self.stop()
                    NotificationCenter.default.post(name: .riqForceLogout, object: nil)
                } else if let err = err {
                    self.lastError = err.localizedDescription
                } else if code >= 400 {
                    self.lastError = "Server answered \(code)"
                } else {
                    self.lastError = nil
                }
                if bgTask != .invalid {
                    UIApplication.shared.endBackgroundTask(bgTask)
                    bgTask = .invalid
                }
            }
        }.resume()
    }

    // MARK: - Reminders

    private func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// The user swiped the app away — iOS stops live tracking. Remind them to reopen it.
    func notifyPausedIfTracking() {
        guard Session.shared.trackingEnabled, Session.shared.isLoggedIn else { return }
        let c = UNMutableNotificationContent()
        c.title = "Location tracking paused"
        c.body = "RecoverIQ was closed. Open it again to keep your route tracking on during duty."
        c.sound = .default
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 2, repeats: false)
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "riq.paused", content: c, trigger: trigger))
    }
}
