import Foundation

/// A fully dynamic JSON value — the Swift stand-in for Kotlin's `Map<String, Any?>` / `Any?` payloads
/// (MIS, RTSB, to-do, monitor, chat, payslips…).
///
/// Reading:   `m["kpis"]?["total"]?.double`, `v.string`, `v.int`, `v.bool`, `v.array`, `v.object`,
///            `v.text` (lossy display string), `v.isNull`, `v.decode(Case.self)` (re-decode into a model).
/// Building:  literals work — `let body: [String: JSONValue] = ["lat": 12.3, "platform": "ios", "x": nil]`
///            or explicit `.double(x)`, `JSONValue(optional)`.
enum JSONValue: Codable, Hashable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let b = try? c.decode(Bool.self) { self = .bool(b); return }
        if let i = try? c.decode(Int.self) { self = .int(i); return }
        if let d = try? c.decode(Double.self) { self = .double(d); return }
        if let s = try? c.decode(String.self) { self = .string(s); return }
        if let a = try? c.decode([JSONValue].self) { self = .array(a); return }
        if let o = try? c.decode([String: JSONValue].self) { self = .object(o); return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unsupported JSON value")
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .int(let i): try c.encode(i)
        case .double(let d): try c.encode(d)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    // MARK: - Convenience initialisers (nil → .null)

    init(_ v: String?) { if let v = v { self = .string(v) } else { self = .null } }
    init(_ v: Int?) { if let v = v { self = .int(v) } else { self = .null } }
    init(_ v: Double?) { if let v = v { self = .double(v) } else { self = .null } }
    init(_ v: Bool?) { if let v = v { self = .bool(v) } else { self = .null } }
    init(_ v: [Int]) { self = .array(v.map { JSONValue.int($0) }) }
    init(_ v: [String]) { self = .array(v.map { JSONValue.string($0) }) }

    // MARK: - Accessors

    var isNull: Bool { if case .null = self { return true }; return false }

    /// String value (numbers/bools are converted).
    var string: String? {
        switch self {
        case .string(let s): return s
        case .int(let i): return String(i)
        case .double(let d): return JSONValue.fmt(d)
        case .bool(let b): return b ? "true" : "false"
        default: return nil
        }
    }

    var int: Int? {
        switch self {
        case .int(let i): return i
        case .double(let d): return d.isFinite ? Int(d) : nil
        case .string(let s): return Int(s.trimmingCharacters(in: .whitespaces)) ?? Double(s).map { Int($0) }
        case .bool(let b): return b ? 1 : 0
        default: return nil
        }
    }

    var double: Double? {
        switch self {
        case .double(let d): return d
        case .int(let i): return Double(i)
        case .string(let s): return Double(s.trimmingCharacters(in: .whitespaces))
        default: return nil
        }
    }

    var bool: Bool? {
        switch self {
        case .bool(let b): return b
        case .int(let i): return i != 0
        case .double(let d): return d != 0
        case .string(let s):
            let l = s.lowercased()
            if l == "true" || l == "1" || l == "yes" { return true }
            if l == "false" || l == "0" || l == "no" { return false }
            return nil
        default: return nil
        }
    }

    var array: [JSONValue]? { if case .array(let a) = self { return a }; return nil }
    var object: [String: JSONValue]? { if case .object(let o) = self { return o }; return nil }

    /// Lossy display text: strings as-is, numbers formatted, null → "", arrays/objects as JSON.
    var text: String {
        switch self {
        case .null: return ""
        case .array, .object:
            if let d = try? JSONEncoder().encode(self), let s = String(data: d, encoding: .utf8) { return s }
            return ""
        default: return string ?? ""
        }
    }

    subscript(key: String) -> JSONValue? {
        if case .object(let o) = self { return o[key] }
        return nil
    }

    subscript(index: Int) -> JSONValue? {
        if case .array(let a) = self, index >= 0, index < a.count { return a[index] }
        return nil
    }

    /// Re-decode this value into any Decodable model (e.g. `row.decode(Case.self)`).
    func decode<T: Decodable>(_ type: T.Type) -> T? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    /// Build a JSONValue from any Encodable model.
    static func from<T: Encodable>(_ value: T) -> JSONValue {
        guard let data = try? JSONEncoder().encode(value),
              let v = try? JSONDecoder().decode(JSONValue.self, from: data) else { return .null }
        return v
    }

    static func fmt(_ d: Double) -> String {
        if d.isFinite && d == d.rounded() && abs(d) < 1e15 { return String(Int(d)) }
        return String(d)
    }

    /// Runtime coercion used by the lenient model decoder (String/Int/Double/Bool targets only).
    func coerce<T>(to type: T.Type) -> T? {
        if T.self == String.self { return string as? T }
        if T.self == Int.self { return int as? T }
        if T.self == Double.self { return double as? T }
        if T.self == Bool.self { return bool as? T }
        return nil
    }
}

extension JSONValue: ExpressibleByStringLiteral, ExpressibleByIntegerLiteral, ExpressibleByFloatLiteral,
    ExpressibleByBooleanLiteral, ExpressibleByNilLiteral, ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral {
    init(stringLiteral value: String) { self = .string(value) }
    init(integerLiteral value: Int) { self = .int(value) }
    init(floatLiteral value: Double) { self = .double(value) }
    init(booleanLiteral value: Bool) { self = .bool(value) }
    init(nilLiteral: ()) { self = .null }
    init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    init(dictionaryLiteral elements: (String, JSONValue)...) {
        var o: [String: JSONValue] = [:]
        for (k, v) in elements { o[k] = v }
        self = .object(o)
    }
}

/// Dictionary helpers for `[String: JSONValue]` payloads (Kotlin `Map<String, Any?>`).
extension Dictionary where Key == String, Value == JSONValue {
    func str(_ k: String) -> String? { self[k]?.string }
    func int(_ k: String) -> Int? { self[k]?.int }
    func dbl(_ k: String) -> Double? { self[k]?.double }
    func bool(_ k: String) -> Bool? { self[k]?.bool }
    func arr(_ k: String) -> [JSONValue] { self[k]?.array ?? [] }
    func obj(_ k: String) -> [String: JSONValue] { self[k]?.object ?? [:] }
    /// Decode the whole dictionary into a model.
    func decode<T: Decodable>(_ type: T.Type) -> T? { JSONValue.object(self).decode(T.self) }
}

// MARK: - Lenient keyed decoding used by every model in Models*.swift
//
// Kotlin/Moshi defaults (`val x: Double = 0.0`) become NON-optional Swift properties:
//   `self.x = c.d(.x, 0.0)`          → value, or the default when missing / null / wrong type
// Nullable Kotlin fields stay optional:
//   `self.y = c.opt(.y)`             → value or nil (never throws)
//   `self.z = c.optOr(.z, false)`    → nullable-with-default (`Boolean? = false`)
// Required (no default, non-null) fields:
//   `self.id = try c.req(.id)`       → throws if missing (like Moshi)
// All of them also accept "stringly"/numeric mismatches (e.g. "12" for an Int, 5 for a String).
extension KeyedDecodingContainer {
    func opt<T: Decodable>(_ key: Key) -> T? {
        if let v = try? decodeIfPresent(T.self, forKey: key) { return v }
        guard let j = try? decodeIfPresent(JSONValue.self, forKey: key) else { return nil }
        return j.coerce(to: T.self)
    }

    func optOr<T: Decodable>(_ key: Key, _ def: T) -> T? {
        if contains(key), (try? decodeNil(forKey: key)) == true { return nil }
        let v: T? = opt(key)
        return v ?? def
    }

    func d<T: Decodable>(_ key: Key, _ def: T) -> T {
        let v: T? = opt(key)
        return v ?? def
    }

    func req<T: Decodable>(_ key: Key) throws -> T {
        let v: T? = opt(key)
        if let v = v { return v }
        return try decode(T.self, forKey: key)   // throws the precise DecodingError
    }
}
