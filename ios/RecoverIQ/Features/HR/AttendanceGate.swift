import SwiftUI
import UIKit
import CoreLocation

/// Port of AttendanceScreens.kt `AttendanceGate`: the daily check-in popup, the 30s presence heartbeat
/// and the shift-end (overtime / check-out) prompt. Mounted once by AppRoot; reads the user from AppState.
struct AttendanceGate: View {
    @EnvironmentObject var app: AppState

    @State private var me: MeToday? = nil
    @State private var showCheckin: Bool = false
    @State private var showOvertime: Bool = false
    @State private var busy: Bool = false
    @State private var checkinErr: String? = nil
    /// Once checked in or dismissed this session, never auto-pop the dialog again (kills any reopen loop).
    @State private var handled: Bool = false
    @State private var photoBytes: Data? = nil
    @State private var photoLoc: CLLocationCoordinate2D? = nil
    @State private var showCamera: Bool = false
    @State private var stamping: Bool = false

    init() {}

    var body: some View {
        Color.clear
            .frame(width: 0, height: 0)
            .allowsHitTesting(false)
            .task(id: app.user?.id ?? -1) { await reload() }
            .task(id: me?.tracked ?? false) { await heartbeatLoop() }
            .sheet(isPresented: checkinBinding, onDismiss: { handled = true }) {
                checkinSheet
            }
            .alert(overtimeTitle, isPresented: $showOvertime) {
                Button("Continue working") { continueWorking() }
                Button("Check out", role: .destructive) { checkOutAndLogout() }
            } message: {
                Text("Check out for the day, or continue working (overtime)? You'll be auto checked-out in 5 minutes if there's no response.")
            }
    }

    // MARK: - Derived

    /// Selfie + GPS check-in follows the PERSON: an FOS, or a TC with the FOS hat, checks in the field way.
    private var isFos: Bool {
        guard let u = app.user else { return false }
        return u.role == "fos" || u.alsoFieldAgent || u.availableViews.contains("fos") || (me?.field ?? false)
    }

    private var checkinBinding: Binding<Bool> {
        Binding<Bool>(
            get: { showCheckin && (me?.needsCheckin ?? false) && app.user != nil },
            set: { v in if !v { showCheckin = false } }
        )
    }

    private var overtimeTitle: String { "Shift ended (\(me?.shiftEnd ?? "19:00"))" }

    private var firstName: String {
        let n: String = app.user?.name ?? ""
        return n.split(separator: " ").first.map { String($0) } ?? n
    }

    // MARK: - Check-in sheet

    private var checkinSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Good day, \(firstName)! Check in to start.")
                        .font(.bodyMedium).foregroundColor(.TextDark)
                    Text("Shift \(me?.shiftStart ?? "09:00")–\(me?.shiftEnd ?? "19:00"). Your time and location are recorded.")
                        .font(.labelSmall).foregroundColor(.Muted)
                    if isFos { photoSection }
                    if let e = checkinErr {
                        Text(e).font(.labelSmall).foregroundColor(.Warn)
                    }
                    HRFilledButton(confirmTitle, enabled: canConfirm) { doCheckin() }
                        .padding(.top, 6)
                    HROutlinedButton("Not now", enabled: !busy) {
                        handled = true
                        showCheckin = false
                    }
                }
                .padding(20)
            }
            .navigationTitle("Check in")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .interactiveDismissDisabled(busy)
        .fullScreenCover(isPresented: $showCamera) {
            HRImagePicker(source: .frontCamera) { img in
                showCamera = false
                if let i = img { processPhoto(i) }
            }
            .ignoresSafeArea()
        }
    }

    @ViewBuilder private var photoSection: some View {
        if let data = photoBytes, let img = UIImage(data: data) {
            Image(uiImage: img)
                .resizable()
                .scaledToFit()
                .frame(maxHeight: 180)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        HROutlinedButton(photoButtonTitle, enabled: !busy && !stamping) { showCamera = true }
        if photoBytes == nil {
            Text("A GPS-tagged check-in photo is required.")
                .font(.labelSmall).foregroundColor(.Warn)
        }
    }

    private var photoButtonTitle: String {
        if stamping { return "Processing photo…" }
        return photoBytes != nil ? "✓ Photo captured · retake" : "📷 Take check-in photo"
    }

    private var confirmTitle: String {
        if busy { return "Checking in…" }
        return isFos ? "Check in with photo" : "Check in"
    }

    private var canConfirm: Bool { !busy && !stamping && (!isFos || photoBytes != nil) }

    // MARK: - Actions

    @MainActor private func reload() async {
        guard app.user != nil else { return }
        me = try? await API.shared.attMeToday()
        if (me?.needsCheckin ?? false) && !handled { showCheckin = true }
    }

    /// Heartbeat every 30s while the app is alive and attendance is tracked for this user.
    @MainActor private func heartbeatLoop() async {
        guard me?.tracked == true else { return }
        while !Task.isCancelled {
            let r: HeartbeatResp? = try? await API.shared.attHeartbeat(active: true)
            if r?.autoLogout == true {
                app.logout()
                break
            }
            if r?.promptOvertime == true { showOvertime = true }
            try? await Task.sleep(nanoseconds: 30_000_000_000)
        }
    }

    private func processPhoto(_ image: UIImage) {
        stamping = true
        let name: String = app.user?.name ?? ""
        Task { @MainActor in
            let loc: CLLocationCoordinate2D? = await AttendanceGate.quickLocation()
            photoLoc = loc
            photoBytes = AttendanceGate.stampCheckinPhoto(image, lat: loc?.latitude, lng: loc?.longitude, name: name)
            stamping = false
        }
    }

    private func doCheckin() {
        busy = true
        checkinErr = nil
        let fos: Bool = isFos
        let bytes: Data? = photoBytes
        let pl: CLLocationCoordinate2D? = photoLoc
        Task { @MainActor in
            var failure: Error? = nil
            do {
                if fos, let b = bytes {
                    _ = try await API.shared.attCheckinPhoto(bytes: b, lat: pl?.latitude, lng: pl?.longitude)
                } else {
                    let loc: CLLocationCoordinate2D? = await AttendanceGate.quickLocation()
                    _ = try await API.shared.attCheckin(lat: loc?.latitude, lng: loc?.longitude)
                }
            } catch {
                failure = error
            }
            busy = false
            if let f = failure {
                // Keep the dialog open WITH the real reason instead of silently flashing back.
                checkinErr = AttendanceGate.checkinErrMsg(f)
            } else {
                // Trust the check-in response — close and refresh once (no re-derived reopen).
                handled = true
                showCheckin = false
                photoBytes = nil
                checkinErr = nil
                me = try? await API.shared.attMeToday()
            }
        }
    }

    private func continueWorking() {
        showOvertime = false
        Task { _ = try? await API.shared.attOvertime() }
    }

    private func checkOutAndLogout() {
        showOvertime = false
        Task { @MainActor in
            let loc: CLLocationCoordinate2D? = await AttendanceGate.quickLocation()
            _ = try? await API.shared.attCheckout(lat: loc?.latitude, lng: loc?.longitude)
            app.logout()
        }
    }

    // MARK: - Static helpers

    /// Kotlin lastKnownLatLng: the system's last fix if fresh, else a short one-shot fix.
    static func quickLocation() async -> CLLocationCoordinate2D? {
        if let l = LocationOnce.lastKnown, Date().timeIntervalSince(l.timestamp) < 300 {
            return l.coordinate
        }
        if let fix = try? await LocationOnce.current(timeout: 10, desiredAccuracy: 100, maxAge: 120) {
            return CLLocationCoordinate2D(latitude: fix.latitude, longitude: fix.longitude)
        }
        return LocationOnce.lastKnown?.coordinate
    }

    /// Turn a failed check-in into a human message (server `detail`, or a network hint).
    static func checkinErrMsg(_ error: Error) -> String {
        if let e = error as? APIError {
            switch e {
            case .http(let code, let detail, _):
                if let d = detail, !d.trimmingCharacters(in: .whitespaces).isEmpty { return d }
                return "Couldn't check in (error \(code)). Please try again."
            case .network:
                return "Network problem — check your connection and try again."
            default:
                return e.localizedDescription
            }
        }
        if (error as NSError).domain == NSURLErrorDomain {
            return "Network problem — check your connection and try again."
        }
        let m: String = error.localizedDescription
        return m.isEmpty ? "Couldn't check in. Please try again." : m
    }

    /// Burn the name + GPS + timestamp onto the check-in photo (bottom strip); JPEG 85%.
    static func stampCheckinPhoto(_ image: UIImage, lat: Double?, lng: Double?, name: String) -> Data? {
        let base: UIImage = HRUtil.scaled(image, maxWidth: 1280)
        let size: CGSize = base.size
        let w: CGFloat = size.width
        let h: CGFloat = size.height
        let ts: CGFloat = w * 0.032
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.dateFormat = "dd MMM yyyy  HH:mm"
        var gps: String = "GPS unavailable"
        if let la = lat, let ln = lng {
            gps = "GPS " + String(format: "%.5f", la) + ", " + String(format: "%.5f", ln)
        }
        let lines: [String] = [name, gps, df.string(from: Date())]
        let boxH: CGFloat = ts * (CGFloat(lines.count) + 0.9)
        let fmt = UIGraphicsImageRendererFormat.default()
        fmt.scale = 1
        let renderer = UIGraphicsImageRenderer(size: size, format: fmt)
        let out: UIImage = renderer.image { ctx in
            base.draw(in: CGRect(origin: .zero, size: size))
            UIColor(white: 0, alpha: 0.667).setFill()
            ctx.fill(CGRect(x: 0, y: h - boxH, width: w, height: boxH))
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: ts),
                .foregroundColor: UIColor.white,
            ]
            var y: CGFloat = h - boxH + ts * 0.15
            for ln in lines {
                (ln as NSString).draw(at: CGPoint(x: w * 0.02, y: y), withAttributes: attrs)
                y += ts * 1.25
            }
        }
        return out.jpegData(compressionQuality: 0.85)
    }
}
