import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Combine

/// Backend WebSocket (`/ws?token=<JWT>`) — port of data/Realtime.kt.
///
/// Usage in screens (Compose `rememberLiveKey()` equivalent):
/// ```
/// .onReceive(Realtime.shared.changed) { _ in Task { await reload() } }
/// ```
/// Publishers (always delivered on the main thread):
///  * `changed`      — "data_changed" / "case_update": something changed on the backend → live-refresh.
///  * `openCase`     — "open_case": the web asked to open this case on the phone (AppRoot pushes it).
///  * `notification` — "notification": targeted message (e.g. new customer address) → banner/local notification.
///  * `broadcast`    — "broadcast": office broadcast (from, body) → AppRoot pops an alert.
/// AppRoot calls `connect()` once signed in and `disconnect()` on sign-out.
final class Realtime: NSObject {
    static let shared = Realtime()

    let changed = PassthroughSubject<Void, Never>()
    let openCase = PassthroughSubject<Int, Never>()
    let notification = PassthroughSubject<NotificationItem, Never>()
    let broadcast = PassthroughSubject<BroadcastMessage, Never>()

    struct BroadcastMessage: Identifiable, Hashable {
        let id: UUID = UUID()
        let from: String
        let body: String
    }

    private var task: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var wantConnected = false
    private var backoff: TimeInterval = 3
    private var pingTimer: Timer?
    private var generation: Int = 0

    private override init() { super.init() }

    /// https://host/ → wss://host/ws ; http://host/ → ws://host/ws
    static func wsURL(token: String) -> URL? {
        var base = Session.baseURL.absoluteString
        while base.hasSuffix("/") { base.removeLast() }
        if base.hasPrefix("https://") { base = "wss://" + base.dropFirst("https://".count) }
        else if base.hasPrefix("http://") { base = "ws://" + base.dropFirst("http://".count) }
        let t = API.encodeQueryComponent(token)
        return URL(string: base + "/ws?token=" + t)
    }

    func connect() {
        DispatchQueue.main.async {
            guard let token = Session.shared.token, !token.isEmpty else { return }
            self.wantConnected = true
            if self.task != nil { return }
            self.backoff = 3
            self.open(token: token)
        }
    }

    func disconnect() {
        DispatchQueue.main.async {
            self.wantConnected = false
            self.generation += 1
            self.pingTimer?.invalidate()
            self.pingTimer = nil
            self.task?.cancel(with: .normalClosure, reason: Data("logout".utf8))
            self.task = nil
            self.urlSession?.invalidateAndCancel()
            self.urlSession = nil
        }
    }

    // MARK: - Internals (main thread)

    private func open(token: String) {
        guard let url = Realtime.wsURL(token: token) else { return }
        generation += 1
        let gen = generation
        var req = URLRequest(url: url)
        req.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")
        req.setValue("RecoverIQ-iOS/" + AppInfo.version, forHTTPHeaderField: "User-Agent")
        let s = URLSession(configuration: .default)
        urlSession = s
        let t = s.webSocketTask(with: req)
        task = t
        t.resume()
        receive(gen: gen)
        pingTimer?.invalidate()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 25, repeats: true) { [weak self] _ in
            self?.sendPing(gen: gen)
        }
    }

    private func sendPing(gen: Int) {
        guard gen == generation, let t = task else { return }
        t.sendPing { [weak self] err in
            if err != nil {
                DispatchQueue.main.async { self?.failed(gen: gen) }
            }
        }
    }

    private func receive(gen: Int) {
        guard let t = task else { return }
        Task { [weak self] in
            var text: String? = nil
            var ok = true
            do {
                let msg = try await t.receive()
                switch msg {
                case .string(let s): text = s
                case .data(let d): text = String(data: d, encoding: .utf8)
                @unknown default: text = nil
                }
            } catch {
                ok = false
            }
            let received: String? = text
            let success: Bool = ok
            DispatchQueue.main.async {
                guard let self = self, gen == self.generation else { return }
                if success {
                    self.backoff = 3
                    if let s = received { self.handle(text: s) }
                    self.receive(gen: gen)
                } else {
                    self.failed(gen: gen)
                }
            }
        }
    }

    private func failed(gen: Int) {
        guard gen == generation else { return }
        generation += 1
        pingTimer?.invalidate()
        pingTimer = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        guard wantConnected else { return }
        let delay = backoff
        backoff = min(backoff * 2, 30)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self = self, self.wantConnected, self.task == nil,
                  let token = Session.shared.token, !token.isEmpty else { return }
            self.open(token: token)
        }
    }

    private func handle(text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONDecoder().decode([String: JSONValue].self, from: data) else { return }
        let type = obj["type"]?.string ?? ""
        switch type {
        case "open_case":
            let id = obj["case_id"]?.int ?? -1
            if id > 0 { openCase.send(id) }
        case "data_changed", "case_update":
            changed.send(())
        case "broadcast":
            let from = obj["from"]?.string ?? ""
            broadcast.send(BroadcastMessage(from: from.isEmpty ? "Head Office" : from, body: obj["body"]?.string ?? ""))
        case "notification":
            if let n = obj["notification"]?.object {
                func s(_ k: String) -> String? {
                    let v = n[k]?.string ?? ""
                    return v.isEmpty ? nil : v
                }
                let cid = n["case_id"]?.int ?? 0
                let item = NotificationItem(id: n["id"]?.int ?? 0, caseId: cid > 0 ? cid : nil, type: s("type"),
                                            title: s("title"), body: s("body"), createdBy: s("created_by"),
                                            createdAt: s("created_at"))
                notification.send(item)
            }
        default:
            break
        }
    }
}
