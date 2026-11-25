import SwiftUI
import UIKit

// Shared helpers for the HR / personal screens (Attendance, Leave, Payslips, Profile, Change Requests).
// All names are HR-prefixed so they never collide with helpers written by other screen groups.

// MARK: - Text field (Kotlin Fld / OutlinedTextField with a label)

struct HRField: View {
    let label: String
    @Binding var text: String
    var secure: Bool = false
    var multiline: Bool = false
    var keyboard: UIKeyboardType = .default

    init(_ label: String, text: Binding<String>, secure: Bool = false, multiline: Bool = false,
         keyboard: UIKeyboardType = .default) {
        self.label = label
        self._text = text
        self.secure = secure
        self.multiline = multiline
        self.keyboard = keyboard
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.labelSmall).foregroundColor(.Muted)
            input
                .font(.bodyMedium)
                .foregroundColor(.TextDark)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
        }
    }

    @ViewBuilder private var input: some View {
        if secure {
            SecureField(label, text: $text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
        } else if multiline {
            TextField(label, text: $text, axis: .vertical)
                .lineLimit(2...5)
                .keyboardType(keyboard)
        } else {
            TextField(label, text: $text)
                .keyboardType(keyboard)
        }
    }
}

// MARK: - Buttons

/// Filled button (Material `Button`).
struct HRFilledButton: View {
    let title: String
    var color: Color = .BrandBlue
    var enabled: Bool = true
    let action: () -> Void

    init(_ title: String, color: Color = .BrandBlue, enabled: Bool = true, action: @escaping () -> Void) {
        self.title = title
        self.color = color
        self.enabled = enabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.labelLarge)
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity)
                .background(RoundedRectangle(cornerRadius: 20).fill(enabled ? color : Color.MutedDim))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

/// Outlined button (Material `OutlinedButton`).
struct HROutlinedButton: View {
    let title: String
    var color: Color = .BrandBlue
    var enabled: Bool = true
    var fill: Bool = true
    let action: () -> Void

    init(_ title: String, color: Color = .BrandBlue, enabled: Bool = true, fill: Bool = true,
         action: @escaping () -> Void) {
        self.title = title
        self.color = color
        self.enabled = enabled
        self.fill = fill
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.labelLarge)
                .foregroundColor(enabled ? color : Color.MutedDim)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .frame(maxWidth: fill ? .infinity : nil)
                .background(RoundedRectangle(cornerRadius: 20).stroke(enabled ? color.opacity(0.6) : Color.MutedDim, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

// MARK: - Image picker (camera / library) — UIImagePickerController wrapper

struct HRImagePicker: UIViewControllerRepresentable {
    enum Source { case camera, frontCamera, library }

    let source: Source
    let onPicked: (UIImage?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onPicked: onPicked) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let p = UIImagePickerController()
        p.delegate = context.coordinator
        p.allowsEditing = false
        let wantsCamera: Bool = (source == .camera || source == .frontCamera)
        if wantsCamera && UIImagePickerController.isSourceTypeAvailable(.camera) {
            p.sourceType = .camera
            p.cameraCaptureMode = .photo
            if source == .frontCamera && UIImagePickerController.isCameraDeviceAvailable(.front) {
                p.cameraDevice = .front
            }
        } else {
            p.sourceType = .photoLibrary
        }
        return p
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onPicked: (UIImage?) -> Void
        init(onPicked: @escaping (UIImage?) -> Void) { self.onPicked = onPicked }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            let img: UIImage? = info[.originalImage] as? UIImage
            onPicked(img)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onPicked(nil)
        }
    }
}

// MARK: - Misc helpers

enum HRUtil {
    /// Kotlin `HttpException → detail` pattern: the FastAPI detail if present, else nil.
    static func detail(_ error: Error) -> String? {
        if let e = error as? APIError, let d = e.detail, !d.trimmingCharacters(in: .whitespaces).isEmpty {
            return d
        }
        return nil
    }

    static func isHTTP(_ error: Error) -> Bool {
        if let e = error as? APIError, e.statusCode != nil { return true }
        return false
    }

    /// Scale an image down to `maxWidth` (keeps aspect) — Kotlin createScaledBitmap.
    static func scaled(_ image: UIImage, maxWidth: CGFloat) -> UIImage {
        let w: CGFloat = image.size.width
        if w <= maxWidth || w <= 0 { return image }
        let h: CGFloat = image.size.height * maxWidth / w
        let fmt = UIGraphicsImageRendererFormat.default()
        fmt.scale = 1
        let r = UIGraphicsImageRenderer(size: CGSize(width: maxWidth, height: h), format: fmt)
        return r.image { _ in image.draw(in: CGRect(x: 0, y: 0, width: maxWidth, height: h)) }
    }

    /// Copy a downloaded temp file to a friendly name (Kotlin cache-file names) and share it.
    static func shareRenamed(_ url: URL, as name: String) {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("riq-hr-" + UUID().uuidString, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let dest = dir.appendingPathComponent(name)
            try FileManager.default.copyItem(at: url, to: dest)
            Files.share(dest)
        } catch {
            Files.share(url)
        }
    }

    /// "%,.0f" style with Western grouping (Kotlin money()/rupees()).
    static func grouped(_ v: Double, decimals: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.locale = Locale(identifier: "en_US")
        f.minimumFractionDigits = decimals
        f.maximumFractionDigits = decimals
        return f.string(from: NSNumber(value: v)) ?? String(format: "%.\(decimals)f", v)
    }
}
