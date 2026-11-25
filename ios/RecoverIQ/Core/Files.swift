import UIKit

/// Save / share downloaded files (Excel, PDF, images) — replaces Android's FileProvider + ACTION_SEND.
///
/// ```
/// let url = try await API.shared.attDownload(month: m)
/// Files.share(url)                       // share sheet: Save to Files, WhatsApp, Mail, Excel…
/// ```
enum Files {

    /// Present the share sheet for a local file URL.
    static func share(_ url: URL) {
        presentShareSheet(items: [url])
    }

    /// Present the share sheet for several files.
    static func share(_ urls: [URL]) {
        presentShareSheet(items: urls)
    }

    /// Write `data` to a temp file called `name` and return its URL.
    static func saveTemp(_ data: Data, name: String) throws -> URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("riq-files-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(name)
        try data.write(to: url, options: .atomic)
        return url
    }

    /// Copy into the app's Documents folder (visible in the Files app → On My iPhone → RecoverIQ,
    /// because UIFileSharingEnabled / LSSupportsOpeningDocumentsInPlace are on).
    @discardableResult
    static func saveToDocuments(_ url: URL) -> URL? {
        guard let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return nil }
        let dest = docs.appendingPathComponent(url.lastPathComponent)
        try? FileManager.default.removeItem(at: dest)
        do {
            try FileManager.default.copyItem(at: url, to: dest)
            return dest
        } catch {
            return nil
        }
    }

    /// UIActivityViewController presented from the top-most view controller of the key window.
    static func presentShareSheet(items: [Any]) {
        DispatchQueue.main.async {
            guard let top = topViewController() else { return }
            let vc = UIActivityViewController(activityItems: items, applicationActivities: nil)
            if let pop = vc.popoverPresentationController {   // iPad
                pop.sourceView = top.view
                pop.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 1, height: 1)
                pop.permittedArrowDirections = []
            }
            top.present(vc, animated: true)
        }
    }

    static var keyWindow: UIWindow? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        for s in scenes where s.activationState == .foregroundActive {
            if let w = s.windows.first(where: { $0.isKeyWindow }) { return w }
        }
        for s in scenes {
            if let w = s.windows.first(where: { $0.isKeyWindow }) ?? s.windows.first { return w }
        }
        return nil
    }

    static func topViewController() -> UIViewController? {
        var top = keyWindow?.rootViewController
        while let p = top?.presentedViewController { top = p }
        return top
    }
}
