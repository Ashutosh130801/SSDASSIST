import CoreLocation
import UIKit
import UserNotifications

/// Always-on FOS location tracking — the iOS counterpart of the Android LocationService.
///
/// Runs in NATIVE code (not the web page), so it keeps reporting while the app is in the
/// background or the phone is locked:
///  • standard GPS updates with `allowsBackgroundLocationUpdates` (blue location pill),
///  • plus significant-location-change monitoring, which makes iOS RELAUNCH the app after a
///    restart / when it was closed, so tracking resumes by itself after ~500 m of movement.
/// Each fix is posted straight to /api/tracking/ping with the saved token + device id.
final class LocationTracker: NSObject, CLLocationManagerDelegate {
    static let shared = LocationTracker()

    private let manager = CLLocationManager()
    private(set) var running = false
    private var lastSentAt = Date.distantPast
    private var lastSentLoc: CLLocation?
    private var inFlight = false
    private(set) var lastFix: CLLocation?
    private(set) var lastError: String?

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
    }

    private var authStatus: CLAuthorizationStatus {
        if #available(iOS 14.0, *) { return manager.authorizationStatus }
        return CLLocationManager.authorizationStatus()
    }

    private var hasBackgroundMode: Bool {
        let modes = Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") as? [String] ?? []
        return modes.contains("location")
    }

    // MARK: - Control

    /// Start (or keep) tracking. Asks for permission the first time: "While Using" first, then iOS
    /// offers "Change to Always Allow", which is what lets tracking run with the screen locked.
    func start() {
        NativeStore.trackingEnabled = true
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
        if !keepEnabled { NativeStore.trackingEnabled = false }
        running = false
        manager.stopUpdatingLocation()
        manager.stopMonitoringSignificantLocationChanges()
        if hasBackgroundMode { manager.allowsBackgroundLocationUpdates = false }
    }

    /// Called at every launch (also silent background relaunches) and when the app becomes active.
    func resumeIfEnabled() {
        guard NativeStore.trackingEnabled, !NativeStore.token.isEmpty else { return }
        guard NativeStore.userRole.isEmpty || NativeStore.userRole == "fos" else { return }
        if !running { start() }
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

    /// For the web page's tracking banner / settings screen.
    func status() -> [String: Any] {
        var perm = "unknown"
        switch authStatus {
        case .authorizedAlways: perm = "always"
        case .authorizedWhenInUse: perm = "when_in_use"
        case .denied: perm = "denied"
        case .restricted: perm = "restricted"
        case .notDetermined: perm = "not_determined"
        @unknown default: perm = "unknown"
        }
        var out: [String: Any] = ["running": running, "enabled": NativeStore.trackingEnabled, "permission": perm,
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
        guard NativeStore.trackingEnabled else { return }
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
        guard NativeStore.trackingEnabled else { return }
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
        let token = NativeStore.token
        guard !token.isEmpty, !inFlight else { return }
        inFlight = true
        lastSentAt = Date()
        lastSentLoc = loc

        var body: [String: Any] = ["latitude": loc.coordinate.latitude, "longitude": loc.coordinate.longitude,
                                   "accuracy": loc.horizontalAccuracy]
        if loc.speed >= 0 { body["speed"] = loc.speed }
        let dev = NativeStore.deviceId
        if !dev.isEmpty { body["device_id"] = dev }

        var req = URLRequest(url: NativeStore.baseURL.appendingPathComponent("api/tracking/ping"))
        req.httpMethod = "POST"
        req.timeoutInterval = 20
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
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
                    NativeStore.token = ""
                    self.stop()
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
        guard NativeStore.trackingEnabled, !NativeStore.token.isEmpty else { return }
        let c = UNMutableNotificationContent()
        c.title = "Location tracking paused"
        c.body = "RecoverIQ was closed. Open it again to keep your route tracking on during duty."
        c.sound = .default
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 2, repeats: false)
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "riq.paused", content: c, trigger: trigger))
    }
}
