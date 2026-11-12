import UIKit
import WebKit

/// Hosts the live RecoverIQ web app and handles everything a browser tab can't do on iPhone:
/// background GPS (via LocationTracker), native geolocation, saving/sharing downloaded files,
/// phone / WhatsApp / maps links, JS alerts & confirms, camera + microphone permission.
final class WebViewController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {

    private var webView: WKWebView!
    private let geo = GeoBridge()
    private let progress = UIProgressView(progressViewStyle: .bar)
    private var progressObs: NSKeyValueObservation?
    private var downloads: [ObjectIdentifier: URL] = [:]
    private var checkedUpdate = false

    private var baseHost: String { NativeStore.baseURL.host?.lowercased() ?? "" }

    // MARK: - Setup

    override func loadView() {
        let root = UIView()
        root.backgroundColor = UIColor(red: 0xF4 / 255, green: 0xF7 / 255, blue: 0xFB / 255, alpha: 1)

        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []
        cfg.applicationNameForUserAgent = "RecoverIQ-iOS/\(AppInfo.version) Mobile/15E148 Safari/604.1"
        let ucc = WKUserContentController()
        ucc.add(WeakScriptHandler(self), name: "riq")
        ucc.addUserScript(WKUserScript(source: Bootstrap.script(), injectionTime: .atDocumentStart, forMainFrameOnly: true))
        cfg.userContentController = ucc

        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.navigationDelegate = self
        wv.uiDelegate = self
        wv.allowsBackForwardNavigationGestures = true
        wv.isOpaque = false
        wv.backgroundColor = root.backgroundColor
        wv.scrollView.backgroundColor = root.backgroundColor
        if #available(iOS 16.4, *) { wv.isInspectable = true }   // Safari ▸ Develop, for troubleshooting
        wv.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(wv)

        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.progressTintColor = UIColor(red: 0x25 / 255, green: 0x63 / 255, blue: 0xEB / 255, alpha: 1)
        root.addSubview(progress)

        let g = root.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            wv.topAnchor.constraint(equalTo: g.topAnchor),
            wv.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            wv.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            wv.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            progress.topAnchor.constraint(equalTo: g.topAnchor),
            progress.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            progress.trailingAnchor.constraint(equalTo: root.trailingAnchor),
        ])
        webView = wv
        view = root

        progressObs = wv.observe(\.estimatedProgress, options: [.new]) { [weak self] w, _ in
            guard let self = self else { return }
            self.progress.isHidden = w.estimatedProgress >= 1
            self.progress.setProgress(Float(w.estimatedProgress), animated: true)
        }
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        webView.load(URLRequest(url: NativeStore.baseURL))
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        if !checkedUpdate { checkedUpdate = true; Updater.check(from: self) }
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        if #available(iOS 13.0, *) { return .darkContent }
        return .default
    }

    // MARK: - JS bridge (window.RIQNative)

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else { return }
        let id = (body["id"] as? NSNumber)?.intValue
        switch cmd {
        case "auth":
            // Web session changed (login / logout / token refresh) — keep the native copy in sync.
            let token = body["token"] as? String ?? ""
            NativeStore.token = token
            if let d = body["device"] as? String { NativeStore.deviceId = d }
            NativeStore.userJSON = body["user"] as? String ?? ""
            if token.isEmpty { LocationTracker.shared.stop() }
            reply(id, ["ok": true])
        case "trackStart":
            if let t = body["token"] as? String, !t.isEmpty { NativeStore.token = t }
            if let d = body["device_id"] as? String { NativeStore.deviceId = d }
            LocationTracker.shared.start()
            reply(id, LocationTracker.shared.status())
        case "trackStop":
            LocationTracker.shared.stop()
            reply(id, ["ok": true])
        case "trackStatus":
            reply(id, LocationTracker.shared.status())
        case "saveFile":
            saveFile(name: body["name"] as? String ?? "download", base64: body["b64"] as? String ?? "")
            reply(id, ["ok": true])
        case "openExternal":
            if let s = body["url"] as? String, let u = URL(string: s) { UIApplication.shared.open(u) }
        case "openSettings":
            if let u = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(u) }
        case "geo":
            handleGeo(body, id: id)
        default:
            break
        }
    }

    private func handleGeo(_ body: [String: Any], id: Int?) {
        guard let id = id else { return }
        let op = body["op"] as? String ?? "get"
        switch op {
        case "watch":
            geo.watch(id: id) { [weak self] r in self?.reply(id, r) }
        case "clear":
            geo.clear(id: id)
        default:
            let maxAge = (body["maxAge"] as? NSNumber)?.doubleValue ?? 0
            geo.get(maxAgeMs: maxAge) { [weak self] r in self?.reply(id, r) }
        }
    }

    private func reply(_ id: Int?, _ data: [String: Any]) {
        guard let id = id,
              let d = try? JSONSerialization.data(withJSONObject: data),
              let json = String(data: d, encoding: .utf8) else { return }
        DispatchQueue.main.async { [weak self] in
            self?.webView.evaluateJavaScript("window.__riqCb && window.__riqCb(\(id), \(json));", completionHandler: nil)
        }
    }

    // MARK: - Files (Excel / PDF / CSV exports)

    private func saveFile(name: String, base64: String) {
        guard let data = Data(base64Encoded: base64, options: .ignoreUnknownCharacters) else {
            alert("Download failed", "The file could not be read."); return
        }
        let safe = name.replacingOccurrences(of: "/", with: "-")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(safe.isEmpty ? "download" : safe)
        do {
            try data.write(to: url, options: .atomic)
            share(url)
        } catch {
            alert("Download failed", error.localizedDescription)
        }
    }

    private func share(_ url: URL) {
        let vc = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        if let pop = vc.popoverPresentationController {          // iPad
            pop.sourceView = view
            pop.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1)
            pop.permittedArrowDirections = []
        }
        topController().present(vc, animated: true)
    }

    // MARK: - Navigation

    private func isOurs(_ url: URL) -> Bool {
        guard let h = url.host?.lowercased() else { return true }
        return h == baseHost || h.hasSuffix("." + baseHost)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.allow); return }
        let scheme = (url.scheme ?? "").lowercased()
        // tel:, whatsapp:, mailto:, sms:, maps, sidestore: … → hand to iOS.
        if !["http", "https", "about", "blob", "data", "file"].contains(scheme) {
            UIApplication.shared.open(url)
            decisionHandler(.cancel); return
        }
        let mainFrame = navigationAction.targetFrame?.isMainFrame ?? true
        // Links leaving RecoverIQ (wa.me, Google Maps, bank sites) open in their own app / Safari.
        if (scheme == "http" || scheme == "https") && mainFrame && !isOurs(url) {
            UIApplication.shared.open(url)
            decisionHandler(.cancel); return
        }
        if #available(iOS 14.5, *), navigationAction.shouldPerformDownload {
            decisionHandler(.download); return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if #available(iOS 14.5, *) {
            let disposition = (navigationResponse.response as? HTTPURLResponse)?
                .value(forHTTPHeaderField: "Content-Disposition")?.lowercased() ?? ""
            if !navigationResponse.canShowMIMEType || disposition.hasPrefix("attachment") {
                decisionHandler(.download); return
            }
        }
        decisionHandler(.allow)
    }

    // A navigation turned into a file download → our WKDownloadDelegate saves + shares it.
    @available(iOS 14.5, *)
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    @available(iOS 14.5, *)
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    // target=_blank / window.open
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, url.absoluteString != "about:blank", !url.absoluteString.isEmpty {
            if isOurs(url) { webView.load(navigationAction.request) } else { UIApplication.shared.open(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        showOffline(error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled { return }
    }

    // iOS killed the page's process (memory) — reload instead of leaving a blank screen.
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    private func showOffline(_ error: Error) {
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled { return }
        if ns.domain == "WebKitErrorDomain" && ns.code == 102 { return }   // frame load interrupted (download)
        let base = NativeStore.baseURL.absoluteString
        let msg = ns.localizedDescription.replacingOccurrences(of: "<", with: "&lt;")
        let html = """
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>body{font-family:-apple-system,system-ui;background:#F4F7FB;color:#0F1B2D;display:flex;align-items:center;
        justify-content:center;height:100vh;margin:0;text-align:center}.c{padding:28px;max-width:340px}
        h2{margin:12px 0 6px}p{color:#64748B;font-size:14px;line-height:1.5}
        a{display:inline-block;margin-top:16px;background:#2563EB;color:#fff;padding:12px 26px;border-radius:12px;
        text-decoration:none;font-weight:600}</style></head>
        <body><div class="c"><div style="font-size:44px">📶</div><h2>Can't reach RecoverIQ</h2>
        <p>Check your internet connection and try again.<br><small>\(msg)</small></p>
        <a href="\(base)">Try again</a></div></body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // MARK: - JS dialogs (alert / confirm / prompt)

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        presentOr(a) { completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        presentOr(a) { completionHandler(false) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        a.addTextField { $0.text = defaultText }
        a.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
        presentOr(a) { completionHandler(nil) }
    }

    // Camera / microphone for the RecoverIQ site itself (visit photos, chat voice calls).
    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        let h = origin.host.lowercased()
        decisionHandler(h == baseHost || h.hasSuffix("." + baseHost) ? .grant : .prompt)
    }

    // MARK: - Helpers

    private func topController() -> UIViewController {
        var top: UIViewController = self
        while let p = top.presentedViewController { top = p }
        return top
    }

    /// Present, or run `fallback` if something else is already on screen (so JS never hangs).
    private func presentOr(_ vc: UIViewController, fallback: @escaping () -> Void) {
        let top = topController()
        if top.isBeingDismissed || top.isBeingPresented || viewIfLoaded?.window == nil { fallback(); return }
        top.present(vc, animated: true)
    }

    func alert(_ title: String, _ message: String) {
        let a = UIAlertController(title: title, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "OK", style: .default))
        topController().present(a, animated: true)
    }
}

// MARK: - Downloads that reach WebKit directly (links with Content-Disposition: attachment)

@available(iOS 14.5, *)
extension WebViewController: WKDownloadDelegate {
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(suggestedFilename.isEmpty ? "download" : suggestedFilename)
        downloads[ObjectIdentifier(download)] = url
        completionHandler(url)
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let url = downloads.removeValue(forKey: ObjectIdentifier(download)) { share(url) }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloads.removeValue(forKey: ObjectIdentifier(download))
        alert("Download failed", error.localizedDescription)
    }
}

/// Breaks the WKUserContentController → handler retain cycle.
final class WeakScriptHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ target: WKScriptMessageHandler) { self.target = target }
    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(c, didReceive: message)
    }
}
