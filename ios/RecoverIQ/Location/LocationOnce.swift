import Foundation
import CoreLocation

/// One GPS fix (visit stamps, check-in).
struct GPSFix {
    let latitude: Double
    let longitude: Double
    let accuracy: Double          // metres (horizontalAccuracy)
    let timestamp: Date
    let isMock: Bool              // iOS 15+: simulated by software (Xcode / spoofing accessory)
    let location: CLLocation

    /// Age of the fix in seconds (sent as gps_fix_age_s).
    var ageSeconds: Double { max(0, Date().timeIntervalSince(timestamp)) }
}

/// Reverse-geocoded address of a fix (sent as gps_pincode / gps_address / gps_city).
struct GeoAddress {
    let pincode: String?
    let address: String?
    let city: String?
}

enum LocationOnceError: LocalizedError {
    case denied
    case timeout
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .denied: return "Location permission is off. Enable it in Settings → RecoverIQ → Location."
        case .timeout: return "Couldn't get a GPS fix. Move to an open area and try again."
        case .failed(let m): return m
        }
    }
}

/// Async one-shot GPS: asks for When-In-Use permission if needed, then returns the best fix it gets
/// within `timeout` seconds (stops early once accuracy ≤ `desiredAccuracy` metres).
///
/// ```
/// let fix = try await LocationOnce.current()
/// let addr = await LocationOnce.reverseGeocode(fix)
/// ```
final class LocationOnce: NSObject, CLLocationManagerDelegate {
    private static var active: [LocationOnce] = []

    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<GPSFix, Error>?
    private var best: CLLocation?
    private var desired: Double = 50
    private var maxAge: TimeInterval = 15
    private var timer: Timer?
    private var started = false

    /// Get a fix (call from any context; work happens on the main thread).
    static func current(timeout: TimeInterval = 20, desiredAccuracy: Double = 50, maxAge: TimeInterval = 15) async throws -> GPSFix {
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<GPSFix, Error>) in
            DispatchQueue.main.async {
                let one = LocationOnce()
                one.desired = desiredAccuracy
                one.maxAge = maxAge
                one.continuation = cont
                active.append(one)
                one.begin(timeout: timeout)
            }
        }
    }

    /// The last fix the system already has (no waiting), if any.
    static var lastKnown: CLLocation? { CLLocationManager().location }

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
    }

    private var status: CLAuthorizationStatus {
        if #available(iOS 14.0, *) { return manager.authorizationStatus }
        return CLLocationManager.authorizationStatus()
    }

    private func begin(timeout: TimeInterval) {
        timer = Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { [weak self] _ in
            self?.finishWithBestOrTimeout()
        }
        switch status {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()   // continues in locationManagerDidChangeAuthorization
        case .denied, .restricted:
            finish(.failure(LocationOnceError.denied))
        default:
            startUpdates()
        }
    }

    private func startUpdates() {
        guard !started else { return }
        started = true
        manager.startUpdatingLocation()
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) { authChanged() }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        if #available(iOS 14.0, *) { return }
        authChanged()
    }

    private func authChanged() {
        switch status {
        case .notDetermined: break
        case .denied, .restricted: finish(.failure(LocationOnceError.denied))
        default: startUpdates()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        for loc in locations where loc.horizontalAccuracy >= 0 {
            if Date().timeIntervalSince(loc.timestamp) > maxAge { continue }   // stale cached fix
            if best == nil || loc.horizontalAccuracy < (best?.horizontalAccuracy ?? .greatestFiniteMagnitude) {
                best = loc
            }
        }
        if let b = best, b.horizontalAccuracy <= desired {
            finish(.success(LocationOnce.makeFix(b)))
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if let e = error as? CLError {
            if e.code == .locationUnknown { return }   // transient, keep waiting
            if e.code == .denied { finish(.failure(LocationOnceError.denied)); return }
        }
        if best == nil { finish(.failure(LocationOnceError.failed(error.localizedDescription))) }
    }

    private func finishWithBestOrTimeout() {
        if let b = best { finish(.success(LocationOnce.makeFix(b))) }
        else { finish(.failure(LocationOnceError.timeout)) }
    }

    private func finish(_ result: Result<GPSFix, Error>) {
        guard let c = continuation else { return }
        continuation = nil
        timer?.invalidate()
        timer = nil
        manager.stopUpdatingLocation()
        manager.delegate = nil
        LocationOnce.active.removeAll { $0 === self }
        switch result {
        case .success(let f): c.resume(returning: f)
        case .failure(let e): c.resume(throwing: e)
        }
    }

    private static func makeFix(_ l: CLLocation) -> GPSFix {
        var mock = false
        if #available(iOS 15.0, *) {
            mock = l.sourceInformation?.isSimulatedBySoftware ?? false
        }
        return GPSFix(latitude: l.coordinate.latitude, longitude: l.coordinate.longitude,
                      accuracy: l.horizontalAccuracy, timestamp: l.timestamp, isMock: mock, location: l)
    }

    // MARK: - Reverse geocoding

    static func reverseGeocode(_ fix: GPSFix) async -> GeoAddress? {
        return await reverseGeocode(lat: fix.latitude, lng: fix.longitude)
    }

    static func reverseGeocode(lat: Double, lng: Double) async -> GeoAddress? {
        let loc = CLLocation(latitude: lat, longitude: lng)
        return await withCheckedContinuation { (cont: CheckedContinuation<GeoAddress?, Never>) in
            let geocoder = CLGeocoder()
            geocoder.reverseGeocodeLocation(loc) { marks, _ in
                _ = geocoder   // keep the geocoder alive until the callback
                guard let p = marks?.first else { cont.resume(returning: nil); return }
                let parts: [String] = [p.name, p.subLocality, p.locality, p.administrativeArea, p.postalCode]
                    .compactMap { $0 }.filter { !$0.isEmpty }
                var seen = Set<String>()
                let unique = parts.filter { seen.insert($0).inserted }
                cont.resume(returning: GeoAddress(pincode: p.postalCode,
                                                  address: unique.isEmpty ? nil : unique.joined(separator: ", "),
                                                  city: p.locality ?? p.subAdministrativeArea))
            }
        }
    }
}
