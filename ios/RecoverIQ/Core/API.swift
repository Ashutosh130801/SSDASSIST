import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

// =====================================================================================
// Network stack — port of data/Api.kt (+ ApiService.kt / Repository.kt in APIEndpoints.swift).
//
//  * Base URL: Info.plist RIQBaseURL (Session.baseURL). Paths are relative, exactly as Retrofit ("api/cases").
//  * Every request: `Authorization: Bearer <token>` (from Session), `ngrok-skip-browser-warning: true`,
//    `User-Agent: RecoverIQ-iOS/<version>`.
//  * HTTP 401 on a request that carried a token → posts `Notification.Name.riqForceLogout`
//    (AppState listens and drops to the login screen) — same as AuthEvents.forceLogout on Android.
//  * Errors → `APIError` (LocalizedError). `error.localizedDescription` is the FastAPI `detail` text.
//  * Query params: `[String: String?]`, nil values skipped (Retrofit @Query semantics), RFC-3986 encoded.
//  * Certificate pinning: intentionally NOT implemented (the server sits behind Cloudflare, which rotates
//    certificates; Android ships with CERT_PIN empty as well). TLS is still enforced by ATS.
//  * Android forces HTTP/1.1 for the Cloudflare tunnel; URLSession negotiates itself (not configurable).
// =====================================================================================

extension Notification.Name {
    /// Posted (on the main thread) when the server rejects our token with 401.
    static let riqForceLogout = Notification.Name("riq.forceLogout")
}

/// Every API failure. `localizedDescription` gives a human-readable message (FastAPI `detail` when present).
enum APIError: LocalizedError {
    case http(code: Int, detail: String?, body: String)
    case network(String)
    case decoding(String)
    case invalidURL(String)
    case notSignedIn

    var errorDescription: String? {
        switch self {
        case .http(let code, let detail, _):
            if let d = detail, !d.isEmpty { return d }
            if code >= 500 { return "Server error (\(code)). Please try again." }
            return "Request failed (\(code))."
        case .network(let m): return m
        case .decoding(let m): return "Unexpected server response: " + m
        case .invalidURL(let u): return "Bad URL: " + u
        case .notSignedIn: return "Not signed in"
        }
    }

    /// HTTP status code (nil for network/decoding errors).
    var statusCode: Int? { if case .http(let c, _, _) = self { return c }; return nil }
    /// FastAPI `detail` text, if any.
    var detail: String? { if case .http(_, let d, _) = self { return d }; return nil }
    /// Raw response body (for e.g. "2FA_REQUIRED" checks).
    var body: String { if case .http(_, _, let b) = self { return b }; return "" }
}

/// One file part of a multipart/form-data request.
struct MultipartFile {
    var name: String          // form field name, e.g. "photo", "file"
    var filename: String      // e.g. "visit.jpg"
    var mimeType: String      // e.g. "image/jpeg"
    var data: Data
}

/// multipart/form-data body builder (Retrofit @Multipart + @Part equivalent).
struct MultipartForm {
    let boundary: String = "RIQBoundary-" + UUID().uuidString
    private(set) var parts: [(name: String, value: String)] = []
    private(set) var files: [MultipartFile] = []

    init() {}

    /// Text field; nil values are skipped (like a null @Part).
    mutating func add(_ name: String, _ value: String?) {
        if let v = value { parts.append((name: name, value: v)) }
    }

    mutating func addFile(_ name: String, filename: String, mimeType: String, data: Data?) {
        if let d = data { files.append(MultipartFile(name: name, filename: filename, mimeType: mimeType, data: d)) }
    }

    var contentType: String { "multipart/form-data; boundary=" + boundary }

    func body() -> Data {
        var d = Data()
        let crlf = "\r\n"
        for p in parts {
            d.append(Data(("--" + boundary + crlf).utf8))
            d.append(Data(("Content-Disposition: form-data; name=\"" + p.name + "\"" + crlf).utf8))
            d.append(Data(("Content-Type: text/plain; charset=utf-8" + crlf + crlf).utf8))
            d.append(Data(p.value.utf8))
            d.append(Data(crlf.utf8))
        }
        for f in files {
            d.append(Data(("--" + boundary + crlf).utf8))
            d.append(Data(("Content-Disposition: form-data; name=\"" + f.name + "\"; filename=\"" + f.filename + "\"" + crlf).utf8))
            d.append(Data(("Content-Type: " + f.mimeType + crlf + crlf).utf8))
            d.append(f.data)
            d.append(Data(crlf.utf8))
        }
        d.append(Data(("--" + boundary + "--" + crlf).utf8))
        return d
    }
}

/// Placeholder for endpoints whose response body we ignore (Kotlin `suspend fun x()` returning Unit).
struct EmptyResponse: Decodable {
    init() {}
    init(from decoder: Decoder) throws {}
}

final class API {
    static let shared = API()

    typealias Query = [String: String?]

    let decoder: JSONDecoder = JSONDecoder()
    let encoder: JSONEncoder = JSONEncoder()
    private let urlSession: URLSession

    private init() {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 45
        cfg.timeoutIntervalForResource = 180
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        urlSession = URLSession(configuration: cfg)
    }

    // MARK: - URL building

    private static let queryAllowed: CharacterSet = {
        var cs = CharacterSet.alphanumerics
        cs.insert(charactersIn: "-._~")
        return cs
    }()

    static func encodeQueryComponent(_ s: String) -> String {
        return s.addingPercentEncoding(withAllowedCharacters: queryAllowed) ?? s
    }

    func makeURL(_ path: String, query: Query = [:]) throws -> URL {
        var p = path
        while p.hasPrefix("/") { p.removeFirst() }
        var s = Session.baseURL.absoluteString + p
        let pairs: [String] = query.keys.sorted().compactMap { k in
            guard let v = query[k] ?? nil else { return nil }
            return API.encodeQueryComponent(k) + "=" + API.encodeQueryComponent(v)
        }
        if !pairs.isEmpty { s += (s.contains("?") ? "&" : "?") + pairs.joined(separator: "&") }
        guard let u = URL(string: s) else { throw APIError.invalidURL(s) }
        return u
    }

    func makeRequest(_ method: String, _ path: String, query: Query = [:], body: Data? = nil,
                     contentType: String? = nil) throws -> URLRequest {
        var req = URLRequest(url: try makeURL(path, query: query))
        req.httpMethod = method
        req.setValue("true", forHTTPHeaderField: "ngrok-skip-browser-warning")
        req.setValue("RecoverIQ-iOS/" + AppInfo.version, forHTTPHeaderField: "User-Agent")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let t = Session.shared.token, !t.isEmpty {
            req.setValue("Bearer " + t, forHTTPHeaderField: "Authorization")
        }
        if let b = body {
            req.httpBody = b
            req.setValue(contentType ?? "application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    // MARK: - Transport

    private func rawData(_ req: URLRequest) async throws -> (Data, URLResponse) {
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<(Data, URLResponse), Error>) in
            let task = urlSession.dataTask(with: req) { data, resp, err in
                if let err = err {
                    cont.resume(throwing: err)
                } else if let resp = resp {
                    cont.resume(returning: (data ?? Data(), resp))
                } else {
                    cont.resume(throwing: APIError.network("No response from server"))
                }
            }
            task.resume()
        }
    }

    /// Performs the request, maps transport errors to readable messages, handles 401 → force logout,
    /// and throws `APIError.http` for any non-2xx status.
    func send(_ req: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let data: Data
        let resp: URLResponse
        do {
            (data, resp) = try await rawData(req)
        } catch let e as APIError {
            throw e
        } catch {
            throw APIError.network(API.networkMessage(error))
        }
        guard let http = resp as? HTTPURLResponse else { throw APIError.network("No response from server") }
        if !(200...299).contains(http.statusCode) {
            let bodyText = String(data: data, encoding: .utf8) ?? ""
            if http.statusCode == 401, req.value(forHTTPHeaderField: "Authorization") != nil {
                DispatchQueue.main.async {
                    NotificationCenter.default.post(name: .riqForceLogout, object: nil)
                }
            }
            throw APIError.http(code: http.statusCode, detail: API.extractDetail(data), body: bodyText)
        }
        return (data, http)
    }

    static func networkMessage(_ error: Error) -> String {
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain {
            switch ns.code {
            case NSURLErrorNotConnectedToInternet: return "No internet connection."
            case NSURLErrorTimedOut: return "Server didn't reply in time. Please try again."
            case NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed:
                return "Can't find the server — check the app's server address / your DNS."
            case NSURLErrorCannotConnectToHost: return "Can't connect to the server (it may be down)."
            case NSURLErrorSecureConnectionFailed, NSURLErrorServerCertificateUntrusted,
                 NSURLErrorServerCertificateHasBadDate, NSURLErrorServerCertificateNotYetValid:
                return "TLS/SSL error reaching the server."
            case NSURLErrorNetworkConnectionLost: return "Network connection lost. Please try again."
            case NSURLErrorCancelled: return "Cancelled."
            default: break
            }
        }
        return "Network error (" + ns.localizedDescription + "). Check your connection."
    }

    /// Pull FastAPI's `detail` (string, list of {msg}, or object) out of an error body.
    static func extractDetail(_ data: Data) -> String? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        let d = obj["detail"] ?? obj["message"] ?? obj["error"]
        if let s = d as? String { return s }
        if let arr = d as? [[String: Any]] {
            let msgs: [String] = arr.compactMap { item in
                guard let m = item["msg"] as? String else { return nil }
                if let loc = item["loc"] as? [Any], let last = loc.last { return "\(last): \(m)" }
                return m
            }
            return msgs.isEmpty ? nil : msgs.joined(separator: "; ")
        }
        if let o = d as? [String: Any] {
            if let m = o["message"] as? String { return m }
            if let m = o["detail"] as? String { return m }
            if let data2 = try? JSONSerialization.data(withJSONObject: o), let s = String(data: data2, encoding: .utf8) { return s }
        }
        return nil
    }

    func decode<T: Decodable>(_ type: T.Type, _ data: Data, _ path: String) throws -> T {
        if T.self == EmptyResponse.self, let e = EmptyResponse() as? T { return e }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding("\(T.self) from \(path): \(API.describe(error))")
        }
    }

    static func describe(_ error: Error) -> String {
        guard let de = error as? DecodingError else { return error.localizedDescription }
        switch de {
        case .keyNotFound(let k, let ctx): return "missing '\(k.stringValue)' at " + ctx.codingPath.map { $0.stringValue }.joined(separator: ".")
        case .typeMismatch(let t, let ctx): return "type \(t) at " + ctx.codingPath.map { $0.stringValue }.joined(separator: ".")
        case .valueNotFound(let t, let ctx): return "null \(t) at " + ctx.codingPath.map { $0.stringValue }.joined(separator: ".")
        case .dataCorrupted(let ctx): return ctx.debugDescription
        @unknown default: return "\(de)"
        }
    }

    // MARK: - Generic verbs (use these in API+<Group>.swift extensions)

    func get<T: Decodable>(_ path: String, query: Query = [:]) async throws -> T {
        let (d, _) = try await send(try makeRequest("GET", path, query: query))
        return try decode(T.self, d, path)
    }

    func post<T: Decodable, B: Encodable>(_ path: String, body: B, query: Query = [:]) async throws -> T {
        let data = try encoder.encode(body)
        let (d, _) = try await send(try makeRequest("POST", path, query: query, body: data))
        return try decode(T.self, d, path)
    }

    /// POST with no request body.
    func post<T: Decodable>(_ path: String, query: Query = [:]) async throws -> T {
        let (d, _) = try await send(try makeRequest("POST", path, query: query))
        return try decode(T.self, d, path)
    }

    func put<T: Decodable, B: Encodable>(_ path: String, body: B, query: Query = [:]) async throws -> T {
        let data = try encoder.encode(body)
        let (d, _) = try await send(try makeRequest("PUT", path, query: query, body: data))
        return try decode(T.self, d, path)
    }

    func patch<T: Decodable, B: Encodable>(_ path: String, body: B, query: Query = [:]) async throws -> T {
        let data = try encoder.encode(body)
        let (d, _) = try await send(try makeRequest("PATCH", path, query: query, body: data))
        return try decode(T.self, d, path)
    }

    func delete<T: Decodable>(_ path: String, query: Query = [:]) async throws -> T {
        let (d, _) = try await send(try makeRequest("DELETE", path, query: query))
        return try decode(T.self, d, path)
    }

    /// Fire a request and ignore the response body (Kotlin Unit endpoints).
    func void(_ method: String, _ path: String, query: Query = [:], json: Data? = nil) async throws {
        _ = try await send(try makeRequest(method, path, query: query, body: json))
    }

    func voidBody<B: Encodable>(_ method: String, _ path: String, body: B, query: Query = [:]) async throws {
        let data = try encoder.encode(body)
        _ = try await send(try makeRequest(method, path, query: query, body: data))
    }

    /// multipart/form-data POST (photo / file uploads).
    func multipart<T: Decodable>(_ path: String, form: MultipartForm, query: Query = [:]) async throws -> T {
        var req = try makeRequest("POST", path, query: query, body: form.body(), contentType: form.contentType)
        req.timeoutInterval = 120
        let (d, _) = try await send(req)
        return try decode(T.self, d, path)
    }

    // MARK: - Downloads (Excel / PDF)

    /// Downloads `path` (GET, or POST with a JSON body) into a temp file named after the server's
    /// Content-Disposition filename and returns its URL. Hand it to `Files.share(url)`.
    func download(path: String, query: Query = [:], method: String = "GET", body: Data? = nil) async throws -> URL {
        var req = try makeRequest(method, path, query: query, body: body)
        req.setValue("*/*", forHTTPHeaderField: "Accept")
        req.timeoutInterval = 180
        let (data, http) = try await send(req)
        let name = API.filename(from: http) ?? API.fallbackName(path: path, http: http)
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("riq-dl-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(name)
        try data.write(to: url, options: .atomic)
        return url
    }

    /// Same as `download(path:…)` but POSTs an Encodable body (e.g. CaseExportRequest).
    func download<B: Encodable>(path: String, postBody: B, query: Query = [:]) async throws -> URL {
        let data = try encoder.encode(postBody)
        return try await download(path: path, query: query, method: "POST", body: data)
    }

    static func filename(from http: HTTPURLResponse) -> String? {
        guard let cd = http.value(forHTTPHeaderField: "Content-Disposition") else { return nil }
        // RFC 5987: filename*=UTF-8''name.xlsx
        if let r = cd.range(of: "filename*=") {
            var v = String(cd[r.upperBound...])
            if let semi = v.firstIndex(of: ";") { v = String(v[..<semi]) }
            if let q = v.range(of: "''") { v = String(v[q.upperBound...]) }
            v = v.trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
            if let dec = v.removingPercentEncoding, !dec.isEmpty { return sanitize(dec) }
        }
        if let r = cd.range(of: "filename=") {
            var v = String(cd[r.upperBound...])
            if let semi = v.firstIndex(of: ";") { v = String(v[..<semi]) }
            v = v.trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
            if !v.isEmpty { return sanitize(v) }
        }
        return nil
    }

    private static func sanitize(_ s: String) -> String {
        let bad = CharacterSet(charactersIn: "/\\:?%*|\"<>")
        let cleaned = s.components(separatedBy: bad).joined(separator: "_")
        return cleaned.isEmpty ? "download" : cleaned
    }

    private static func fallbackName(path: String, http: HTTPURLResponse) -> String {
        var last = path.split(separator: "/").last.map(String.init) ?? "download"
        if let q = last.firstIndex(of: "?") { last = String(last[..<q]) }
        if last.contains(".") { return sanitize(last) }
        let mime = (http.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
        if mime.contains("pdf") { return sanitize(last) + ".pdf" }
        if mime.contains("spreadsheet") || mime.contains("excel") { return sanitize(last) + ".xlsx" }
        if mime.contains("csv") { return sanitize(last) + ".csv" }
        if mime.contains("zip") { return sanitize(last) + ".zip" }
        return sanitize(last)
    }
}
