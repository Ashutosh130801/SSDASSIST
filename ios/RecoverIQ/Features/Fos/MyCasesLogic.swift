import Foundation

// Pure helpers for MyCasesView (port of the local functions / CASE_FILTERS / CASE_SORTS in
// ui/fos/FieldAgentScreens.kt). Kept free of SwiftUI so the view bodies stay small.

struct FosCaseFilter {
    let label: String
    let test: (Case) -> Bool
}

struct FosCaseSort {
    let label: String
    /// Returns true when a should come before b (strict).
    let before: (Case, Case) -> Bool
}

struct FosPortfolio: Identifiable {
    let key: String          // "bank||product"
    let bank: String
    let product: String
    let cases: [Case]
    var id: String { key }
    var pending: Double { cases.reduce(0.0) { $0 + $1.pendingAmount } }
}

struct FosPinCount: Identifiable {
    let pin: String
    let count: Int
    var id: String { pin }
}

enum FosCaseLogic {

    static let filters: [FosCaseFilter] = [
        FosCaseFilter(label: "All", test: { _ in true }),
        FosCaseFilter(label: "To do", test: { c in c.workState == "fresh" }),
        FosCaseFilter(label: "Not visited", test: { c in !(c.visited == true || c.visitedToday == true) }),
        FosCaseFilter(label: "Visited", test: { c in c.visited == true || c.visitedToday == true }),
        FosCaseFilter(label: "Unpaid", test: { c in (c.paidStatus ?? "").uppercased() == "UNPAID" }),
        FosCaseFilter(label: "Paid", test: { c in (c.paidStatus ?? "").uppercased() == "PAID" }),
        FosCaseFilter(label: "PTP", test: { c in
            let d: String = (c.disposition ?? "").uppercased()
            return d == "PTP" || d == "RTP"
        }),
        FosCaseFilter(label: "🚩 Escalated", test: { c in c.escalated == true }),
        FosCaseFilter(label: "🔖 Flagged", test: { c in
            !(c.reviewColor ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }),
    ]

    // Pending amount only, ascending (default) or descending; plus pending-to-NORM / STAB.
    static let sorts: [FosCaseSort] = [
        FosCaseSort(label: "Pending ↑", before: { a, b in a.pendingAmount < b.pendingAmount }),
        FosCaseSort(label: "Pending ↓", before: { a, b in a.pendingAmount > b.pendingAmount }),
        FosCaseSort(label: "Pending NORM ↓", before: { a, b in (a.remainingToNorm ?? 0.0) > (b.remainingToNorm ?? 0.0) }),
        FosCaseSort(label: "Pending STAB ↓", before: { a, b in (a.remainingToStab ?? 0.0) > (b.remainingToStab ?? 0.0) }),
    ]

    /// Stable sort (Kotlin sortedWith / sortedBy are stable; Swift's sort is not).
    static func stableSorted<T>(_ items: [T], by before: (T, T) -> Bool) -> [T] {
        let indexed: [(Int, T)] = Array(items.enumerated()).map { ($0.offset, $0.element) }
        let sorted: [(Int, T)] = indexed.sorted { x, y in
            if before(x.1, y.1) { return true }
            if before(y.1, x.1) { return false }
            return x.0 < y.0
        }
        return sorted.map { $0.1 }
    }

    private static func trimmed(_ s: String?) -> String {
        return (s ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Case month = the upload period ('2026-11'); the sheet's free-text month is only a fallback.
    static func monthOf(_ c: Case) -> String {
        let p: String = trimmed(c.period)
        if !p.isEmpty { return p }
        let m: String = trimmed(c.month)
        if !m.isEmpty { return m }
        return "—"
    }

    /// '2026-11' -> 'Nov 2026' (anything else shown as-is; "—" -> "No month").
    static func monthLabel(_ m: String) -> String {
        let names: [String] = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        let chars: [Character] = Array(m)
        let isPattern: Bool = chars.count == 7 && chars[4] == "-" &&
            chars[0..<4].allSatisfy { $0.isASCII && $0.isNumber } &&
            chars[5..<7].allSatisfy { $0.isASCII && $0.isNumber }
        if !isPattern { return m == "—" ? "No month" : m }
        let year: String = String(chars[0..<4])
        let mi: Int = Int(String(chars[5..<7])) ?? 0
        if mi >= 1 && mi <= 12 { return "\(names[mi - 1]) \(year)" }
        return m
    }

    static func portKey(_ c: Case) -> String {
        return "\(c.bank ?? "—")||\(c.product ?? "—")"
    }

    static func splitKey(_ key: String) -> (String, String) {
        if let r = key.range(of: "||") {
            return (String(key[key.startIndex..<r.lowerBound]), String(key[r.upperBound...]))
        }
        return (key, key)
    }

    private static func digitsOnly(_ s: String) -> String {
        return String(s.filter { $0.isASCII && $0.isNumber })
    }

    /// All PIN codes on a case (address 1/2/3), digits only, ≥ 6 digits → first 6, distinct.
    static func pinsOf(_ c: Case) -> [String] {
        var out: [String] = []
        for p in [c.pincode, c.pincode2, c.pincode3] {
            guard let raw = p else { continue }
            let d: String = digitsOnly(raw)
            if d.count >= 6 {
                let six: String = String(d.prefix(6))
                if !out.contains(six) { out.append(six) }
            }
        }
        return out
    }

    /// PIN / area match: digits match any PIN code; words match any address (area, street, landmark).
    static func areaMatch(_ c: Case, _ raw: String) -> Bool {
        let t: String = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if t.isEmpty { return true }
        let d: String = digitsOnly(t)
        if d.count >= 3 && d.count == t.replacingOccurrences(of: " ", with: "").count {
            return pinsOf(c).contains { $0.hasPrefix(d) || $0.contains(d) }
        }
        let addrs: [String] = [c.address, c.address2, c.address3, c.newAddress].compactMap { $0 }
        return addrs.contains { $0.lowercased().contains(t) }
    }

    /// Free-text search inside a portfolio: name / account / card / phone / address, plus digit match.
    static func matches(_ c: Case, _ q: String) -> Bool {
        if q.isEmpty { return true }
        let fields: [String?] = [c.customerName, c.accountNo, c.cardNo, c.phone, c.altPhone,
                                 c.address, c.address2, c.address3, c.newAddress]
        if fields.contains(where: { v in
            guard let s = v else { return false }
            return s.lowercased().contains(q)
        }) { return true }
        let digits: String = digitsOnly(q)
        if digits.isEmpty { return false }
        let numeric: [String?] = [c.accountNo, c.cardNo, c.phone, c.altPhone]
        if numeric.contains(where: { v in
            guard let s = v else { return false }
            return digitsOnly(s).contains(digits)
        }) { return true }
        return pinsOf(c).contains { $0.contains(digits) }
    }

    /// Distinct months, sorted descending (Kotlin sortedDescending on strings).
    static func months(_ cases: [Case]) -> [String] {
        var seen: [String] = []
        for c in cases {
            let m: String = monthOf(c)
            if !seen.contains(m) { seen.append(m) }
        }
        return seen.sorted { $0 > $1 }
    }

    /// groupBy(portKey) keeping first-encounter order, then sortedByDescending(size) (stable).
    static func portfolios(_ cases: [Case]) -> [FosPortfolio] {
        var order: [String] = []
        var groups: [String: [Case]] = [:]
        for c in cases {
            let k: String = portKey(c)
            if groups[k] == nil { order.append(k); groups[k] = [] }
            groups[k]?.append(c)
        }
        let list: [FosPortfolio] = order.map { k in
            let parts: (String, String) = splitKey(k)
            return FosPortfolio(key: k, bank: parts.0, product: parts.1, cases: groups[k] ?? [])
        }
        return stableSorted(list) { a, b in a.cases.count > b.cases.count }
    }

    /// PIN codes with account counts (busiest first, stable on first appearance).
    static func pinCounts(_ cases: [Case]) -> [FosPinCount] {
        var order: [String] = []
        var counts: [String: Int] = [:]
        for c in cases {
            for p in pinsOf(c) {
                if counts[p] == nil { order.append(p); counts[p] = 0 }
                counts[p] = (counts[p] ?? 0) + 1
            }
        }
        let list: [FosPinCount] = order.map { FosPinCount(pin: $0, count: counts[$0] ?? 0) }
        return stableSorted(list) { a, b in a.count > b.count }
    }

    static func sumPending(_ cases: [Case]) -> Double {
        return cases.reduce(0.0) { $0 + $1.pendingAmount }
    }

    static func plural(_ n: Int) -> String { n == 1 ? "" : "s" }

    /// Kotlin: "Cases_${bank}_${prod}_$month".replace(Regex("[^A-Za-z0-9_-]"), "")
    static func exportBase(bank: String, product: String, month: String) -> String {
        let raw: String = "Cases_\(bank)_\(product)_\(month)"
        let kept = raw.unicodeScalars.filter { s in
            (s.value >= 48 && s.value <= 57) || (s.value >= 65 && s.value <= 90) ||
                (s.value >= 97 && s.value <= 122) || s == "_" || s == "-"
        }
        var out: String = ""
        out.unicodeScalars.append(contentsOf: kept)
        return out
    }
}
