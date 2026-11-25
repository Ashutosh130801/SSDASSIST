import Foundation

/// Date helpers — port of ui/common/DateUtil.kt.
/// Server timestamps are UTC (naive on SQLite) and are shown in IST; calendar dates ("yyyy-MM-dd") are shown as-is.
enum DateUtil {
    static let ist: TimeZone = TimeZone(identifier: "Asia/Kolkata") ?? TimeZone(secondsFromGMT: 19800)!
    static let utc: TimeZone = TimeZone(identifier: "UTC") ?? TimeZone(secondsFromGMT: 0)!
    private static let posix = Locale(identifier: "en_US_POSIX")

    private static func fmt(_ pattern: String, _ tz: TimeZone) -> DateFormatter {
        let f = DateFormatter()
        f.locale = posix
        f.timeZone = tz
        f.dateFormat = pattern
        return f
    }

    private static let isoLocal = fmt("yyyy-MM-dd", TimeZone.current)
    private static let isoUtc = fmt("yyyy-MM-dd", utc)
    private static let tsUtc = fmt("yyyy-MM-dd'T'HH:mm:ss", utc)
    private static let pretty = fmt("dd MMM, hh:mm a", ist)
    private static let prettyDate = fmt("dd MMM yyyy", utc)
    private static let monthLbl = fmt("MMM yyyy", utc)

    /// ISO date (UTC) from epoch millis.
    static func isoFromMillis(_ millis: Int64) -> String {
        return isoUtc.string(from: Date(timeIntervalSince1970: Double(millis) / 1000.0))
    }

    /// Epoch millis (UTC midnight) for an ISO date.
    static func millisFromIso(_ isoDate: String?) -> Int64? {
        guard let d = dateFromIso(isoDate) else { return nil }
        return Int64(d.timeIntervalSince1970 * 1000.0)
    }

    /// UTC-midnight Date for "yyyy-MM-dd…" (nil if blank/invalid).
    static func dateFromIso(_ isoDate: String?) -> Date? {
        guard let s = isoDate?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        return isoUtc.date(from: String(s.prefix(10)))
    }

    /// "yyyy-MM-dd" for a Date picked in a DatePicker (local calendar day).
    static func iso(_ date: Date) -> String { isoLocal.string(from: date) }

    /// Local-calendar Date for an ISO day (to seed a SwiftUI DatePicker).
    static func localDate(_ isoDate: String?) -> Date? {
        guard let s = isoDate?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        return isoLocal.date(from: String(s.prefix(10)))
    }

    /// Inclusive day count between two ISO dates (start & end counted); min 1.
    static func daysInclusive(_ startIso: String, _ endIso: String) -> Int {
        guard let a = millisFromIso(startIso), let b = millisFromIso(endIso) else { return 1 }
        let d = Int((b - a) / 86_400_000) + 1
        return d < 1 ? 1 : d
    }

    /// ISO date `days` from today, e.g. plusDaysIso(1) = tomorrow.
    static func plusDaysIso(_ days: Int) -> String {
        let d = Calendar.current.date(byAdding: .day, value: days, to: Date()) ?? Date()
        return isoLocal.string(from: d)
    }

    static func todayIso() -> String { plusDaysIso(0) }

    /// Current month "yyyy-MM".
    static func thisMonth() -> String { String(todayIso().prefix(7)) }

    /// Parse a backend timestamp (UTC, optional fraction / zone) → Date.
    static func parseTimestamp(_ isoTs: String?) -> Date? {
        guard let s = isoTs?.trimmingCharacters(in: .whitespaces), s.count >= 19 else { return nil }
        let head = String(s.prefix(19)).replacingOccurrences(of: " ", with: "T")
        guard var d = tsUtc.date(from: head) else { return nil }
        // Respect an explicit offset if present (e.g. +05:30 / Z after the seconds/fraction).
        let tail = String(s.dropFirst(19))
        if let r = tail.range(of: "[+-]\\d{2}:?\\d{2}$", options: .regularExpression) {
            let off = String(tail[r]).replacingOccurrences(of: ":", with: "")
            let sign: Double = off.hasPrefix("-") ? -1 : 1
            let digits = off.dropFirst()
            let hh = Double(digits.prefix(2)) ?? 0
            let mm = Double(digits.suffix(2)) ?? 0
            d = d.addingTimeInterval(-sign * (hh * 3600 + mm * 60))
        }
        return d
    }

    /// Best-effort pretty-print of a backend ISO timestamp ("05 Mar, 02:30 PM" IST); falls back to the raw string.
    static func humanTime(_ isoTs: String?) -> String {
        guard let s = isoTs, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return "" }
        if let d = parseTimestamp(s) { return pretty.string(from: d) }
        return String(s.prefix(16)).replacingOccurrences(of: "T", with: " ")
    }

    /// "05 Mar 2025" for an ISO date/timestamp; falls back to the first 10 chars.
    static func humanDate(_ isoTs: String?) -> String {
        guard let s = isoTs, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return "" }
        if let d = isoUtc.date(from: String(s.prefix(10))) { return prettyDate.string(from: d) }
        return String(s.prefix(10))
    }

    /// "Mar 2025" for "2025-03" / "2025-03-…".
    static func monthLabel(_ ym: String?) -> String {
        guard let s = ym, s.count >= 7, let d = isoUtc.date(from: String(s.prefix(7)) + "-01") else { return ym ?? "" }
        return monthLbl.string(from: d)
    }
}
