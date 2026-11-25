import Foundation

// Admin group extensions (Dashboards / Live map / MIS). Only things missing from APIEndpoints.swift.

/// MIS payload + the backend's key order for the key/value blocks (Swift dictionaries are unordered,
/// the Kotlin/Moshi LinkedHashMap kept the server order).
struct MisPayload {
    var data: [String: JSONValue]
    var keyOrder: [String: [String]]
}

extension API {

    private func misQuery(bank: String, product: String, monthBucket: String?, area: String?, branch: String?,
                          cycles: String?, fosIds: String?, callerIds: String?, paid: String?) -> Query {
        return ["bank": bank, "product": product, "month_bucket": API.nb(monthBucket), "area": API.nb(area),
                "branch": API.nb(branch), "cycles": API.nb(cycles), "fos_ids": API.nb(fosIds),
                "caller_ids": API.nb(callerIds), "paid": API.nb(paid)]
    }

    /// GET /api/mis — same query as `mis(...)`, but also returns the object key order of `orderedBlocks`.
    func misOrdered(bank: String, product: String, monthBucket: String? = nil, area: String? = nil,
                    branch: String? = nil, cycles: String? = nil, fosIds: String? = nil, callerIds: String? = nil,
                    paid: String? = nil, orderedBlocks: [String]) async throws -> MisPayload {
        let q: Query = misQuery(bank: bank, product: product, monthBucket: monthBucket, area: area, branch: branch,
                                cycles: cycles, fosIds: fosIds, callerIds: callerIds, paid: paid)
        let url: URL = try await download(path: "api/mis", query: q)
        let raw: Data = try Data(contentsOf: url)
        try? FileManager.default.removeItem(at: url.deletingLastPathComponent())
        let dict: [String: JSONValue] = try JSONDecoder().decode([String: JSONValue].self, from: raw)
        let order: [String: [String]] = JSONKeyOrder.extract(raw, blocks: Set(orderedBlocks))
        return MisPayload(data: dict, keyOrder: order)
    }

    /// GET /api/mis/download — styled Excel of every MIS table for the current filters.
    func misDownload(bank: String, product: String, monthBucket: String? = nil, area: String? = nil,
                     branch: String? = nil, cycles: String? = nil, fosIds: String? = nil,
                     callerIds: String? = nil, paid: String? = nil) async throws -> URL {
        let q: Query = misQuery(bank: bank, product: product, monthBucket: monthBucket, area: area, branch: branch,
                                cycles: cycles, fosIds: fosIds, callerIds: callerIds, paid: paid)
        return try await download(path: "api/mis/download", query: q)
    }

    /// GET /api/mis/pivot-xlsx — the team's MIS pivot workbook filled from live data.
    func misPivotXlsx(bank: String, product: String, monthBucket: String? = nil,
                      branch: String? = nil) async throws -> URL {
        let q: Query = ["bank": bank, "product": product, "month_bucket": API.nb(monthBucket),
                        "branch": API.nb(branch)]
        return try await download(path: "api/mis/pivot-xlsx", query: q)
    }
}

/// Tiny JSON scanner that records, for each top-level key in `blocks` whose value is an object,
/// that object's keys in document order. Never throws; returns what it could read.
enum JSONKeyOrder {
    static func extract(_ data: Data, blocks: Set<String>) -> [String: [String]] {
        let bytes: [UInt8] = [UInt8](data)
        var p = Parser(b: bytes)
        var out: [String: [String]] = [:]
        p.skipWS()
        guard p.peek() == UInt8(ascii: "{") else { return out }
        p.i += 1
        while true {
            p.skipWS()
            if p.peek() == UInt8(ascii: "}") || p.atEnd { break }
            guard let key = p.readString() else { break }
            p.skipWS()
            guard p.peek() == UInt8(ascii: ":") else { break }
            p.i += 1
            p.skipWS()
            if blocks.contains(key) && p.peek() == UInt8(ascii: "{") {
                out[key] = p.readObjectKeys()
            } else {
                if !p.skipValue() { break }
            }
            p.skipWS()
            if p.peek() == UInt8(ascii: ",") { p.i += 1; continue }
            break
        }
        return out
    }

    private struct Parser {
        let b: [UInt8]
        var i: Int = 0

        init(b: [UInt8]) { self.b = b }

        var atEnd: Bool { i >= b.count }

        func peek() -> UInt8? { i < b.count ? b[i] : nil }

        mutating func skipWS() {
            while i < b.count {
                let c = b[i]
                if c == 0x20 || c == 0x0A || c == 0x0D || c == 0x09 { i += 1 } else { break }
            }
        }

        mutating func readString() -> String? {
            guard peek() == UInt8(ascii: "\"") else { return nil }
            let start = i
            i += 1
            while i < b.count {
                let c = b[i]
                if c == UInt8(ascii: "\\") { i += 2; continue }
                if c == UInt8(ascii: "\"") { i += 1; break }
                i += 1
            }
            let end = min(i, b.count)
            let slice: [UInt8] = Array(b[start..<end])
            if let s = try? JSONDecoder().decode(String.self, from: Data(slice)) { return s }
            return String(decoding: slice.dropFirst().dropLast(), as: UTF8.self)
        }

        mutating func readObjectKeys() -> [String] {
            var keys: [String] = []
            guard peek() == UInt8(ascii: "{") else { return keys }
            i += 1
            while true {
                skipWS()
                if peek() == UInt8(ascii: "}") { i += 1; break }
                guard let k = readString() else { break }
                keys.append(k)
                skipWS()
                guard peek() == UInt8(ascii: ":") else { break }
                i += 1
                skipWS()
                if !skipValue() { break }
                skipWS()
                if peek() == UInt8(ascii: ",") { i += 1; continue }
                if peek() == UInt8(ascii: "}") { i += 1 }
                break
            }
            return keys
        }

        /// Skips any JSON value (string / number / literal / nested object / array).
        mutating func skipValue() -> Bool {
            guard let c = peek() else { return false }
            if c == UInt8(ascii: "\"") { return readString() != nil }
            if c == UInt8(ascii: "{") || c == UInt8(ascii: "[") {
                var depth = 0
                while i < b.count {
                    let ch = b[i]
                    if ch == UInt8(ascii: "\"") { _ = readString(); continue }
                    if ch == UInt8(ascii: "{") || ch == UInt8(ascii: "[") { depth += 1 }
                    if ch == UInt8(ascii: "}") || ch == UInt8(ascii: "]") {
                        depth -= 1
                        if depth == 0 { i += 1; return true }
                    }
                    i += 1
                }
                return false
            }
            while i < b.count {
                let ch = b[i]
                if ch == UInt8(ascii: ",") || ch == UInt8(ascii: "}") || ch == UInt8(ascii: "]") { break }
                i += 1
            }
            return true
        }
    }
}
