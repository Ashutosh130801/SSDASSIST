import SwiftUI
import UIKit
import CoreImage
import CoreImage.CIFilterBuiltins

/// Renders a string as a QR code (2FA authenticator setup, UPI pay QR) — port of ui/common/Qr.kt.
///
/// `if let img = Qr.image("otpauth://…") { Image(uiImage: img).interpolation(.none).resizable().frame(width: 220, height: 220) }`
/// or simply `QrImage(content: link, size: 220)`.
enum Qr {
    private static let context = CIContext()

    static func image(_ content: String, size: CGFloat = 512) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(content.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage, output.extent.width > 0 else { return nil }
        let scale = max(1, floor(size / output.extent.width))
        let scaled = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let cg = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    /// Kotlin name.
    static func bitmap(_ content: String, size: CGFloat = 512) -> UIImage? { image(content, size: size) }
}

struct QrImage: View {
    let content: String
    var size: CGFloat = 220

    init(content: String, size: CGFloat = 220) {
        self.content = content
        self.size = size
    }

    var body: some View {
        Group {
            if let img = Qr.image(content, size: size * 3) {
                Image(uiImage: img)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
            } else {
                Text("QR unavailable").font(.bodySmall).foregroundColor(.Muted)
            }
        }
        .frame(width: size, height: size)
        .background(Color.white)
    }
}
