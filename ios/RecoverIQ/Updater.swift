import UIKit

/// Checks /downloads/ios.json on the RecoverIQ server. When a newer build is published, offers a
/// one-tap update through SideStore (or AltStore), which re-signs and installs it over this one.
enum Updater {
    static func check(from vc: UIViewController) {
        let url = NativeStore.baseURL.appendingPathComponent("downloads/ios.json")
        var req = URLRequest(url: url)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.timeoutInterval = 15
        URLSession.shared.dataTask(with: req) { data, resp, _ in
            guard (resp as? HTTPURLResponse)?.statusCode == 200, let data = data,
                  let info = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return }
            let latest = (info["version_code"] as? NSNumber)?.intValue ?? 0
            guard latest > AppInfo.build else { return }
            let name = info["version_name"] as? String ?? "\(latest)"
            let file = info["file"] as? String ?? "RecoverIQ.ipa"
            let ipa = NativeStore.baseURL.appendingPathComponent("downloads/" + file).absoluteString
            DispatchQueue.main.async { prompt(vc, version: name, ipa: ipa, notes: info["notes"] as? String) }
        }.resume()
    }

    private static func prompt(_ vc: UIViewController, version: String, ipa: String, notes: String?) {
        let msg = "RecoverIQ v\(version) is available." + (notes.map { "\n\n" + $0 } ?? "")
            + "\n\nIt installs through SideStore / AltStore and keeps your login."
        let a = UIAlertController(title: "Update available", message: msg, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Update now", style: .default) { _ in open(ipa: ipa) })
        a.addAction(UIAlertAction(title: "Later", style: .cancel))
        var top = vc
        while let p = top.presentedViewController { top = p }
        top.present(a, animated: true)
    }

    private static func open(ipa: String) {
        let enc = ipa.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ipa
        let candidates = ["sidestore://install?url=" + enc, "altstore://install?url=" + enc, ipa]
        for s in candidates {
            if let u = URL(string: s), UIApplication.shared.canOpenURL(u) {
                UIApplication.shared.open(u); return
            }
        }
        if let u = URL(string: ipa) { UIApplication.shared.open(u) }
    }
}
