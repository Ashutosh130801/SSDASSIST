import CoreLocation

/// Native `navigator.geolocation` for the web page (visit GPS stamps, check-in, maps).
/// Using Core Location directly avoids WKWebView's repeated "website would like your location"
/// prompts and gives the same accuracy as the background tracker.
final class GeoBridge: NSObject, CLLocationManagerDelegate {
    typealias Callback = ([String: Any]) -> Void

    private let manager = CLLocationManager()
    private var oneShots: [Callback] = []
    private var watchers: [Int: Callback] = [:]
    private var waitingForAuth = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
    }

    private var authStatus: CLAuthorizationStatus {
        if #available(iOS 14.0, *) { return manager.authorizationStatus }
        return CLLocationManager.authorizationStatus()
    }

    /// One position. `maxAgeMs` lets a recent fix be reused (like the web API's maximumAge).
    func get(maxAgeMs: Double, _ cb: @escaping Callback) {
        let recent = [LocationTracker.shared.lastFix, manager.location].compactMap { $0 }
            .sorted { $0.timestamp > $1.timestamp }.first
        if let r = recent, maxAgeMs > 0, Date().timeIntervalSince(r.timestamp) * 1000 <= maxAgeMs {
            cb(Self.payload(r)); return
        }
        oneShots.append(cb)
        if !ensureAuthorized() { return }
        if watchers.isEmpty { manager.requestLocation() }   // a running watch will deliver the next fix
    }

    func watch(id: Int, _ cb: @escaping Callback) {
        watchers[id] = cb
        if ensureAuthorized() { manager.startUpdatingLocation() }
    }

    func clear(id: Int) {
        watchers.removeValue(forKey: id)
        if watchers.isEmpty { manager.stopUpdatingLocation() }
    }

    /// true = authorized now; false = waiting for the prompt or denied (callbacks get an error).
    private func ensureAuthorized() -> Bool {
        switch authStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            return true
        case .notDetermined:
            waitingForAuth = true
            manager.requestWhenInUseAuthorization()
            return false
        default:
            failAll(code: 1, message: "Location permission denied. Turn it on in Settings → RecoverIQ → Location.")
            return false
        }
    }

    private func failAll(code: Int, message: String) {
        let err: [String: Any] = ["ok": false, "code": code, "message": message]
        let shots = oneShots; oneShots.removeAll()
        shots.forEach { $0(err) }
        watchers.values.forEach { $0(err) }
    }

    static func payload(_ l: CLLocation) -> [String: Any] {
        var coords: [String: Any] = ["latitude": l.coordinate.latitude, "longitude": l.coordinate.longitude,
                                     "accuracy": l.horizontalAccuracy, "altitude": l.altitude,
                                     "altitudeAccuracy": l.verticalAccuracy]
        coords["heading"] = l.course >= 0 ? (l.course as Any) : (NSNull() as Any)
        coords["speed"] = l.speed >= 0 ? (l.speed as Any) : (NSNull() as Any)
        return ["ok": true, "coords": coords, "timestamp": l.timestamp.timeIntervalSince1970 * 1000]
    }

    // MARK: - CLLocationManagerDelegate

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) { authChanged() }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        if #available(iOS 14.0, *) { return }
        authChanged()
    }

    private func authChanged() {
        guard waitingForAuth else { return }
        switch authStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            waitingForAuth = false
            if !watchers.isEmpty { manager.startUpdatingLocation() } else if !oneShots.isEmpty { manager.requestLocation() }
        case .denied, .restricted:
            waitingForAuth = false
            failAll(code: 1, message: "Location permission denied. Turn it on in Settings → RecoverIQ → Location.")
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let l = locations.last else { return }
        let p = Self.payload(l)
        let shots = oneShots; oneShots.removeAll()
        shots.forEach { $0(p) }
        watchers.values.forEach { $0(p) }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if let e = error as? CLError, e.code == .locationUnknown, !watchers.isEmpty { return }
        let denied = (error as? CLError)?.code == .denied
        let err: [String: Any] = ["ok": false, "code": denied ? 1 : 2, "message": error.localizedDescription]
        let shots = oneShots; oneShots.removeAll()
        shots.forEach { $0(err) }
        if denied { watchers.values.forEach { $0(err) } }
    }
}
