import SwiftUI
import UIKit

extension Notification.Name {
    /// Post with userInfo ["message": String] to show a toast from non-View code (AppState listens).
    static let riqToast = Notification.Name("riq.toast")
}

/// Show a toast from anywhere (AppRoot renders it).
func showToast(_ message: String) {
    DispatchQueue.main.async {
        NotificationCenter.default.post(name: .riqToast, object: nil, userInfo: ["message": message])
    }
}

/// Device actions shared across screens — port of ui/common/Actions.kt.
///   Actions.call(phone)                      tel: dialer            (Kotlin dial)
///   Actions.dialViaZoiper(phone)             zoiper:<n> → dialer fallback
///   Actions.whatsApp(phone, text: "…")       wa.me deep link        (Kotlin whatsapp)
///   Actions.navigate(lat:lng:address:)       Google Maps app if installed, else Apple Maps
///   Actions.mapsSearch(query)                search an address text in Maps
///   Actions.shareVisit(message:photoJpeg:paymentPhotoJpeg:)  share sheet (WhatsApp is offered there)
///   Actions.share(text:) / Actions.share(items:)            system share sheet
///   Actions.upiLink(...) / Actions.openUpi(...)             UPI pay intent (upi://pay?...)
///   Actions.open(urlString)
enum Actions {

    static func cleanPhone(_ raw: String) -> String {
        return String(raw.filter { $0.isNumber || $0 == "+" })
    }

    /// Normalise to a WhatsApp msisdn (digits only, default +91 for local 10-digit numbers).
    static func waNumber(_ phone: String?) -> String {
        var p = cleanPhone(phone ?? "")
        if p.hasPrefix("+") {
            p.removeFirst()
        } else {
            var local = p
            while local.hasPrefix("0") { local.removeFirst() }
            p = local.count == 10 ? "91" + local : local
        }
        return p
    }

    @discardableResult
    static func open(_ urlString: String) -> Bool {
        guard let u = URL(string: urlString) else { return false }
        if UIApplication.shared.canOpenURL(u) {
            UIApplication.shared.open(u)
            return true
        }
        return false
    }

    // MARK: - Phone

    static func call(_ phone: String?) {
        let p = cleanPhone(phone ?? "")
        if p.isEmpty { showToast("No phone number on file"); return }
        guard let u = URL(string: "tel:" + p) else { return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok { showToast("Calling isn't available on this device") }
        }
    }

    /// Kotlin name.
    static func dial(_ phone: String?) { call(phone) }

    /// Place the call through the Zoiper softphone ("zoiper:<number>"); falls back to the dialer.
    static func dialViaZoiper(_ phone: String?, scheme: String = "zoiper") {
        let p = cleanPhone(phone ?? "")
        if p.isEmpty { showToast("No phone number on file"); return }
        guard let u = URL(string: scheme + ":" + p) else { call(phone); return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok {
                showToast("Zoiper not installed — opening dialer")
                call(phone)
            }
        }
    }

    // MARK: - WhatsApp

    static func whatsApp(_ phone: String?, text: String? = nil) {
        let p = waNumber(phone)
        if p.isEmpty { showToast("No phone number on file"); return }
        var url = "https://wa.me/" + p
        if let t = text, !t.isEmpty {
            url += "?text=" + (t.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "")
        }
        guard let u = URL(string: url) else { return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok { showToast("WhatsApp not available") }
        }
    }

    /// Kotlin name (`Actions.whatsapp(ctx, phone, message)`).
    static func whatsapp(_ phone: String?, message: String? = nil) { whatsApp(phone, text: message) }

    // MARK: - Maps

    private static var hasGoogleMaps: Bool {
        guard let u = URL(string: "comgooglemaps://") else { return false }
        return UIApplication.shared.canOpenURL(u)
    }

    /// Turn-by-turn navigation to a coordinate (Google Maps app if present, else Apple Maps).
    static func navigate(lat: Double?, lng: Double?, address: String? = nil) {
        guard let la = lat, let lo = lng else {
            if let a = address, !a.isEmpty { mapsSearch(a) } else { showToast("No location saved for this case") }
            return
        }
        let ll = String(la) + "," + String(lo)
        if hasGoogleMaps, let u = URL(string: "comgooglemaps://?daddr=" + ll + "&directionsmode=driving") {
            UIApplication.shared.open(u)
            return
        }
        let name = (address ?? "Destination").addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "Destination"
        if let u = URL(string: "http://maps.apple.com/?daddr=" + ll + "&dirflg=d&q=" + name) {
            UIApplication.shared.open(u)
        }
    }

    /// Kotlin `navigate(ctx, lat, lng, label)` spelling.
    static func navigate(_ lat: Double?, _ lng: Double?, label: String?) { navigate(lat: lat, lng: lng, address: label) }

    /// Search an address TEXT in Maps (Google Maps app if present, else Apple Maps).
    static func mapsSearch(_ query: String?) {
        guard let raw = query, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            showToast("No address"); return
        }
        let q = raw.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ") + ", India"
        let enc = q.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? q
        if hasGoogleMaps, let u = URL(string: "comgooglemaps://?q=" + enc) {
            UIApplication.shared.open(u)
            return
        }
        if let u = URL(string: "http://maps.apple.com/?q=" + enc) {
            UIApplication.shared.open(u)
        }
    }

    // MARK: - Sharing

    /// Share sheet with arbitrary items (String, URL, UIImage, Data-as-file URL…).
    static func share(items: [Any]) {
        Files.presentShareSheet(items: items)
    }

    static func share(text: String) { share(items: [text]) }

    /// Visit summary (+ geotagged photo + payment screenshot) via the share sheet — WhatsApp,
    /// WhatsApp Business, Mail… (iOS can't pre-attach images to a WhatsApp deep link).
    static func shareVisit(message: String, photoJpeg: Data?, paymentPhotoJpeg: Data? = nil) {
        var items: [Any] = [message]
        let ts = Int(Date().timeIntervalSince1970)
        if let p = photoJpeg, let u = writeTemp(p, name: "visit_\(ts).jpg") { items.append(u) }
        if let p = paymentPhotoJpeg, let u = writeTemp(p, name: "payment_\(ts).jpg") { items.append(u) }
        share(items: items)
    }

    /// Kotlin shareVisitToSelf — iOS has no "send to this exact chat with attachment" API → share sheet.
    static func shareVisitToSelf(selfPhone: String?, message: String, photoJpeg: Data?) {
        if photoJpeg == nil {
            whatsApp(selfPhone, text: message)
        } else {
            shareVisit(message: message, photoJpeg: photoJpeg)
        }
    }

    private static func writeTemp(_ data: Data, name: String) -> URL? {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("shared", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let u = dir.appendingPathComponent(name)
        do {
            try data.write(to: u, options: .atomic)
            return u
        } catch {
            return nil
        }
    }

    // MARK: - UPI

    /// upi://pay?pa=<vpa>&pn=<payee>&am=<amount>&cu=INR&tn=<note>
    static func upiLink(vpa: String, payee: String?, amount: Double?, note: String? = nil) -> String {
        func enc(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? s }
        var s = "upi://pay?pa=" + enc(vpa)
        if let p = payee, !p.isEmpty { s += "&pn=" + enc(p) }
        if let a = amount, a > 0 { s += "&am=" + String(format: "%.2f", a) }
        s += "&cu=INR"
        if let n = note, !n.isEmpty { s += "&tn=" + enc(n) }
        return s
    }

    /// Opens an installed UPI app (GPay / PhonePe / Paytm / BHIM) with the pay intent.
    static func openUpi(vpa: String, payee: String?, amount: Double?, note: String? = nil) {
        let link = upiLink(vpa: vpa, payee: payee, amount: amount, note: note)
        guard let u = URL(string: link) else { return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok { showToast("No UPI app found — share the QR instead") }
        }
    }
}
