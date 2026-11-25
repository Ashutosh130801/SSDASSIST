import SwiftUI
import UIKit
import MapKit
import CoreLocation

// In-app camera / photo-library picker + the "GPS Map Camera" style stamp burned into the visit
// photo (port of the stamp helpers in ui/detail/VisitDialog.kt: decodeSampled / applyExifRotation /
// fetchMapThumb / wrap / accuracyLabel / stampPhoto). The stamped JPEG itself is proof of where /
// when the visit happened: agent, case, visited address, detected address, PIN, accuracy, lat/lng, IST time.

// MARK: - Picker

/// UIImagePickerController wrapper. Uses the camera when available, else falls back to the photo library.
struct DetailImagePicker: UIViewControllerRepresentable {
    let preferCamera: Bool
    let onPick: (UIImage?) -> Void

    init(preferCamera: Bool, onPick: @escaping (UIImage?) -> Void) {
        self.preferCamera = preferCamera
        self.onPick = onPick
    }

    static var cameraAvailable: Bool {
        return UIImagePickerController.isSourceTypeAvailable(.camera)
    }

    func makeCoordinator() -> Coordinator { Coordinator(onPick: onPick) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let vc = UIImagePickerController()
        if preferCamera && DetailImagePicker.cameraAvailable {
            vc.sourceType = .camera
            vc.cameraCaptureMode = .photo
        } else {
            vc.sourceType = .photoLibrary
        }
        vc.allowsEditing = false
        vc.delegate = context.coordinator
        return vc
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onPick: (UIImage?) -> Void

        init(onPick: @escaping (UIImage?) -> Void) {
            self.onPick = onPick
        }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            let img: UIImage? = info[.originalImage] as? UIImage
            onPick(img)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onPick(nil)
        }
    }
}

// MARK: - Stamp

/// Everything printed on the stamp panel.
struct VisitStampInfo {
    var lat: Double?
    var lng: Double?
    var acc: Double?
    var address: String?
    var agentName: String?
    var caseLabel: String?
    var visitedLabel: String?
    var pincode: String?
    var mapThumb: UIImage?
}

/// Tiny box so the snapshot timeout and completion resume the continuation only once (both run on main).
private final class DetailOnceBox {
    var done: Bool = false
}

enum VisitStamp {

    static func accuracyLabel(_ acc: Double?) -> String {
        guard let a = acc else { return "unknown" }
        let m: String = String(Int(a))
        if a <= 10 { return "±" + m + " m (Excellent)" }
        if a <= 30 { return "±" + m + " m (Good)" }
        if a <= 100 { return "±" + m + " m (Fair)" }
        return "±" + m + " m (Weak)"
    }

    /// Drop ", India" and the pincode from the detected text — the pincode is printed on its own line.
    static func cleanAddress(_ raw: String?, pin: String?) -> String? {
        guard var s = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
        if s.hasSuffix(", India") { s = String(s.dropLast(7)) }
        if s.hasSuffix("India") && s.count > 5 { s = String(s.dropLast(5)) }
        if let p = pin, !p.isEmpty {
            s = s.replacingOccurrences(of: ", " + p, with: "")
            s = s.replacingOccurrences(of: " " + p, with: "")
            s = s.replacingOccurrences(of: p, with: "")
        }
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix(",") { s = String(s.dropLast()).trimmingCharacters(in: .whitespaces) }
        return s.isEmpty ? nil : s
    }

    /// Redraw upright (applies the EXIF orientation) and downscale so the longest side ≤ maxPx.
    static func normalized(_ img: UIImage, maxPx: CGFloat) -> UIImage {
        let pw: CGFloat = img.size.width * img.scale
        let ph: CGFloat = img.size.height * img.scale
        let longest: CGFloat = max(pw, ph)
        let f: CGFloat = longest > maxPx ? maxPx / longest : 1.0
        let target: CGSize = CGSize(width: max(1, floor(pw * f)), height: max(1, floor(ph * f)))
        let fmt = UIGraphicsImageRendererFormat.default()
        fmt.scale = 1
        fmt.opaque = true
        let r = UIGraphicsImageRenderer(size: target, format: fmt)
        return r.image { _ in
            img.draw(in: CGRect(origin: .zero, size: target))
        }
    }

    /// Small Apple-Maps thumbnail centred on the fix with a red pin (Kotlin fetchMapThumb / Google snapshot).
    @MainActor
    static func mapSnapshot(lat: Double, lng: Double, timeout: Double = 3.0) async -> UIImage? {
        let center = CLLocationCoordinate2D(latitude: lat, longitude: lng)
        let opts = MKMapSnapshotter.Options()
        opts.region = MKCoordinateRegion(center: center, latitudinalMeters: 350, longitudinalMeters: 350)
        opts.size = CGSize(width: 300, height: 300)
        opts.traitCollection = UITraitCollection(displayScale: 2)
        let snapper = MKMapSnapshotter(options: opts)
        let box = DetailOnceBox()
        return await withCheckedContinuation { (cont: CheckedContinuation<UIImage?, Never>) in
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                if box.done { return }
                box.done = true
                snapper.cancel()
                cont.resume(returning: nil)
            }
            snapper.start(with: DispatchQueue.main) { (snap: MKMapSnapshotter.Snapshot?, _: Error?) in
                if box.done { return }
                box.done = true
                guard let s = snap else {
                    cont.resume(returning: nil)
                    return
                }
                let pinned: UIImage = drawPin(on: s.image, at: s.point(for: center))
                cont.resume(returning: pinned)
            }
        }
    }

    private static func drawPin(on img: UIImage, at p: CGPoint) -> UIImage {
        let fmt = UIGraphicsImageRendererFormat.default()
        fmt.scale = img.scale
        let r = UIGraphicsImageRenderer(size: img.size, format: fmt)
        return r.image { ctx in
            img.draw(at: .zero)
            let rad: CGFloat = img.size.width * 0.07
            let cg = ctx.cgContext
            cg.setFillColor(UIColor(white: 0, alpha: 0.27).cgColor)
            cg.fillEllipse(in: CGRect(x: p.x - rad, y: p.y, width: rad * 2, height: rad * 2))
            cg.setFillColor(UIColor(red: 0.937, green: 0.267, blue: 0.267, alpha: 1).cgColor)
            cg.fillEllipse(in: CGRect(x: p.x - rad, y: p.y - rad, width: rad * 2, height: rad * 2))
            let inner: CGFloat = rad * 0.38
            cg.setFillColor(UIColor.white.cgColor)
            cg.fillEllipse(in: CGRect(x: p.x - inner, y: p.y - inner, width: inner * 2, height: inner * 2))
        }
    }

    private static func width(_ s: String, _ attrs: [NSAttributedString.Key: Any]) -> CGFloat {
        return (s as NSString).size(withAttributes: attrs).width
    }

    /// Split into ≤ maxLines lines that fit maxWidth, ellipsizing the last one (Kotlin wrap).
    static func wrap(_ text: String, attrs: [NSAttributedString.Key: Any], maxWidth: CGFloat, maxLines: Int) -> [String] {
        if text.trimmingCharacters(in: .whitespaces).isEmpty { return [] }
        let words: [String] = text.components(separatedBy: " ")
        var lines: [String] = []
        var cur: String = ""
        for w in words {
            let trial: String = cur.isEmpty ? w : cur + " " + w
            if width(trial, attrs) <= maxWidth {
                cur = trial
            } else {
                if !cur.isEmpty { lines.append(cur) }
                cur = w
                if lines.count == maxLines - 1 { break }
            }
        }
        if !cur.isEmpty && lines.count < maxLines { lines.append(cur) }
        if let last = lines.last, width(last, attrs) > maxWidth {
            var s: String = last
            while !s.isEmpty && width(s + "…", attrs) > maxWidth { s.removeLast() }
            lines[lines.count - 1] = s + "…"
        }
        return lines
    }

    private static let istFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "Asia/Kolkata") ?? TimeZone(secondsFromGMT: 19800)
        f.dateFormat = "dd MMM yyyy, hh:mm:ss a"
        return f
    }()

    /// Draw the translucent geo-stamp banner across the bottom of the photo (Kotlin stampPhoto).
    static func stamp(_ src: UIImage, _ info: VisitStampInfo) -> UIImage {
        let w: CGFloat = src.size.width * src.scale
        let h: CGFloat = src.size.height * src.scale
        let scale: CGFloat = max(w / 1080.0, 0.5)
        let pad: CGFloat = 20 * scale
        let big: CGFloat = 42 * scale
        let small: CGFloat = 34 * scale
        let edge: CGFloat = 10 * scale

        let shadow = NSShadow()
        shadow.shadowBlurRadius = 4 * scale
        shadow.shadowOffset = .zero
        shadow.shadowColor = UIColor.black

        let bodyAttrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: small),
            .foregroundColor: UIColor.white,
            .shadow: shadow,
        ]
        let titleAttrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.boldSystemFont(ofSize: big),
            .foregroundColor: UIColor.white,
            .shadow: shadow,
        ]
        let labelAttrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.boldSystemFont(ofSize: small),
            .foregroundColor: UIColor(red: 0.992, green: 0.902, blue: 0.541, alpha: 1),   // #FDE68A
            .shadow: shadow,
        ]

        let thumb: UIImage? = info.mapThumb
        let mapSize: CGFloat = thumb != nil ? 300 * scale : 0
        let mapGap: CGFloat = thumb != nil ? pad : 0
        let textW: CGFloat = w - pad * 2 - edge - mapSize - mapGap

        // (text, highlighted)
        var body: [(String, Bool)] = []
        func add(_ lines: [String]) { for l in lines { body.append((l, false)) } }
        if let a = CaseText.nb(info.agentName) { add(wrap("Agent: " + a, attrs: bodyAttrs, maxWidth: textW, maxLines: 1)) }
        if let c = CaseText.nb(info.caseLabel) { add(wrap(c, attrs: bodyAttrs, maxWidth: textW, maxLines: 1)) }
        if let v = CaseText.nb(info.visitedLabel) { add(wrap("Visiting: " + v, attrs: bodyAttrs, maxWidth: textW, maxLines: 1)) }
        body.append(("📍 Detected address", true))
        if let addr = CaseText.nb(info.address) {
            add(wrap(addr, attrs: bodyAttrs, maxWidth: textW, maxLines: 3))
        } else {
            body.append(("Address not available (no internet at photo time)", false))
        }
        let pinText: String = CaseText.nb(info.pincode) ?? "—"
        body.append(("PIN: " + pinText + "     GPS accuracy: " + accuracyLabel(info.acc), true))
        if let la = info.lat, let lo = info.lng {
            body.append(("Lat " + String(format: "%.6f", la) + "   Lng " + String(format: "%.6f", lo), false))
        } else {
            body.append(("Location unavailable", false))
        }
        body.append((istFormatter.string(from: Date()) + " IST", false))

        let lineGap: CGFloat = 1.28
        let textBlockH: CGFloat = pad * 2 + big * lineGap + small * lineGap * CGFloat(body.count)
        let panelH: CGFloat = max(textBlockH, mapSize + pad * 2)
        let top: CGFloat = h - panelH

        let fmt = UIGraphicsImageRendererFormat.default()
        fmt.scale = 1
        fmt.opaque = true
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: w, height: h), format: fmt)
        return renderer.image { ctx in
            src.draw(in: CGRect(x: 0, y: 0, width: w, height: h))
            let cg = ctx.cgContext
            cg.setFillColor(UIColor(white: 0, alpha: 185.0 / 255.0).cgColor)
            cg.fill(CGRect(x: 0, y: top, width: w, height: panelH))
            cg.setFillColor(UIColor(red: 0.231, green: 0.510, blue: 0.965, alpha: 1).cgColor)   // #3B82F6
            cg.fill(CGRect(x: 0, y: top, width: edge, height: panelH))

            if let t = thumb {
                let mx: CGFloat = w - pad - mapSize
                let my: CGFloat = top + (panelH - mapSize) / 2.0
                let frame: CGFloat = 3 * scale
                cg.setFillColor(UIColor.white.cgColor)
                cg.fill(CGRect(x: mx - frame, y: my - frame, width: mapSize + frame * 2, height: mapSize + frame * 2))
                t.draw(in: CGRect(x: mx, y: my, width: mapSize, height: mapSize))
            }

            let x: CGFloat = pad + edge
            var y: CGFloat = top + pad
            ("RecoverIQ • Field visit" as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: titleAttrs)
            y += big * lineGap
            for item in body {
                let attrs: [NSAttributedString.Key: Any] = item.1 ? labelAttrs : bodyAttrs
                (item.0 as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: attrs)
                y += small * lineGap
            }
        }
    }
}
