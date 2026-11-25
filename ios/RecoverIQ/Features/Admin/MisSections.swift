import SwiftUI
import Charts

// MisScreen.kt MisBody / KvBlock / MisTable — renders every block of the generic `/api/mis` payload.

struct MisCol {
    let key: String
    let header: String
    init(_ key: String, _ header: String) { self.key = key; self.header = header }
}

struct MisTableDef {
    let key: String
    let title: String
    let cols: [MisCol]
}

enum MisDefs {
    static let moneyHeaders: Set<String> = [
        "ENR", "PAID ENR", "PENDING", "COLLECTED", "CASH COLL", "TARGET ENR",
        "ACHIEVED ENR", "GAP ENR", "ROLLBACK COLL", "VALUE",
    ]

    static let groupCols: [MisCol] = [
        MisCol("label", "NAME"), MisCol("count", "COUNT"), MisCol("paid", "PAID"), MisCol("unpaid", "UNPAID"),
        MisCol("enr", "ENR"), MisCol("paid_enr", "PAID ENR"), MisCol("pct", "PAID %"), MisCol("norm_pct", "NORM %"),
        MisCol("stab_pct", "STAB %"), MisCol("rollback_pct", "ROLLBACK %"), MisCol("rollback_collected", "ROLLBACK COLL"),
        MisCol("amount", "CASH COLL"), MisCol("visited", "VISITED"), MisCol("not_visited", "NOT VISITED"),
    ]
    static let areaCols: [MisCol] = [
        MisCol("label", "AREA"), MisCol("count", "COUNT"), MisCol("paid", "PAID"), MisCol("unpaid", "UNPAID"),
        MisCol("enr", "ENR"), MisCol("pending", "PENDING"), MisCol("amount", "COLLECTED"), MisCol("recovery_pct", "RECOVERY %"),
        MisCol("pct", "PAID %"), MisCol("norm_pct", "NORM %"), MisCol("stab_pct", "STAB %"),
    ]
    static let caseListCols: [MisCol] = [
        MisCol("customer", "Customer"), MisCol("account", "Account"), MisCol("pending", "Pending"), MisCol("enr", "ENR"),
        MisCol("propensity", "Score"), MisCol("fos", "FOS"), MisCol("caller", "Caller"), MisCol("contacted", "Contacted"),
    ]
    static let nsCaseListCols: [MisCol] = [
        MisCol("customer", "Customer"), MisCol("account", "Account"), MisCol("norm", "NORM"),
        MisCol("pending_norm", "Pending NORM"), MisCol("stab", "STAB"), MisCol("pending_stab", "Pending STAB"),
        MisCol("pending", "Pending"), MisCol("fos", "FOS"), MisCol("caller", "Caller"), MisCol("contacted", "Contacted"),
    ]
    static let leaderboardCols: [MisCol] = [
        MisCol("emp", "EMP NAME"), MisCol("count", "COUNT"), MisCol("unpaid", "UNPAID"), MisCol("paid", "PAID"),
        MisCol("enr", "ENR"), MisCol("target_pct", "TARGET %"), MisCol("target_enr", "TARGET ENR"),
        MisCol("achieved_pct", "ACHIEVED %"), MisCol("achieved_enr", "ACHIEVED ENR"), MisCol("gap_enr", "GAP ENR"),
        MisCol("to_target_pct", "TO TARGET %"), MisCol("status", "STATUS"), MisCol("pending_visit", "PENDING VISIT"),
        MisCol("cash_coll", "CASH COLL"),
    ]

    /// (key, title, columns) in the same order the web MIS lists them.
    static let tables: [MisTableDef] = [
        MisTableDef(key: "leaderboard", title: "Employee performance & leaderboard", cols: leaderboardCols),
        MisTableDef(key: "by_fos", title: "FOS-wise", cols: groupCols),
        MisTableDef(key: "by_caller", title: "Caller-wise", cols: groupCols),
        MisTableDef(key: "by_area", title: "Area-wise recovery", cols: areaCols),
        MisTableDef(key: "by_team_lead", title: "Team-lead wise", cols: groupCols),
        MisTableDef(key: "by_cat", title: "Category-wise", cols: groupCols),
        MisTableDef(key: "by_dpd", title: "Bucket (DPD) recovery", cols: groupCols),
        MisTableDef(key: "aging", title: "Contact aging",
                    cols: [MisCol("label", "Recency"), MisCol("count", "Count"), MisCol("pending", "Pending")]),
        MisTableDef(key: "untouched_table", title: "Untouched high-value cases", cols: caseListCols),
        MisTableDef(key: "top_by_norm", title: "High-value by NORM", cols: nsCaseListCols),
        MisTableDef(key: "top_by_stab", title: "High-value by STAB", cols: nsCaseListCols),
        MisTableDef(key: "top_pending", title: "Top pending cases", cols: caseListCols),
        MisTableDef(key: "priority", title: "Propensity worklist", cols: caseListCols),
        MisTableDef(key: "obstacles", title: "Obstacle rates",
                    cols: [MisCol("caller", "Caller"), MisCol("total", "Total"), MisCol("obstacles", "Obstacles"),
                           MisCol("rate_pct", "Rate %")]),
        MisTableDef(key: "productivity", title: "Productivity (today)",
                    cols: [MisCol("emp", "Employee"), MisCol("calls_today", "Calls today"),
                           MisCol("visits_today", "Visits today"), MisCol("idle", "Idle")]),
        MisTableDef(key: "field_efficiency", title: "FOS field efficiency",
                    cols: [MisCol("fos", "FOS"), MisCol("visits", "Visits"), MisCol("distance_km", "Distance km"),
                           MisCol("off_location", "Off-location"), MisCol("collected", "Collected")]),
        MisTableDef(key: "trend", title: "Collection trend (30d)",
                    cols: [MisCol("date", "Date"), MisCol("collected", "Collected")]),
    ]

    /// dict blocks shown as key/value cards, in web order.
    static let kvBlocks: [(String, String)] = [
        ("overall", "Overall summary"),
        ("settlement", "Settlement leakage & realization"),
        ("projection", "Month-end projection"),
        ("funnel", "Conversion & PTP funnel"),
    ]

    /// Format one cell the way the web MIS shows it: % columns as %, money columns with ₹, the rest plain.
    static func fmtCell(_ header: String, _ v: JSONValue?) -> String {
        guard let v = v else { return "—" }
        switch v {
        case .null: return "—"
        case .bool(let b): return b ? "Yes" : "—"
        case .array, .object: return v.text
        default: break
        }
        if let num = v.double, num.isFinite {
            if header.contains("%") { return String(format: "%.1f%%", num) }
            if moneyHeaders.contains(header.uppercased()) { return inr(num) }
            if num == num.rounded() { return groupedInt(num) }
            return String(format: "%.2f", num)
        }
        return v.text
    }

    private static func groupedInt(_ v: Double) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        f.locale = Locale(identifier: "en_US")
        return f.string(from: NSNumber(value: v)) ?? String(format: "%.0f", v)
    }

    static func prettyKey(_ k: String) -> String {
        let s = k.replacingOccurrences(of: "_", with: " ")
        guard let first = s.first else { return s }
        return String(first).uppercased() + String(s.dropFirst())
    }

    static func rows(_ v: JSONValue?) -> [[String: JSONValue]] {
        guard let arr = v?.array else { return [] }
        return arr.compactMap { $0.object }
    }
}

// MARK: - Body

struct MisBodyView: View {
    let payload: MisPayload

    private var d: [String: JSONValue] { payload.data }

    private var trends: Trends? {
        guard let tr = d["trends"]?.object, !tr.isEmpty else { return nil }
        return Trends(ftd: tr.dbl("ftd") ?? 0, mtd: tr.dbl("mtd") ?? 0,
                      lmtd: tr.dbl("lmtd") ?? 0, overall: tr.dbl("overall") ?? 0)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MisHeaderCard(d: d)
            if let t = trends {
                InfoCard { TrendStrip(trends: t, title: "Cash collected — FTD / MTD / LMTD / Overall") }
            }
            ForEach(0..<MisDefs.kvBlocks.count, id: \.self) { i in
                MisKvSection(key: MisDefs.kvBlocks[i].0, title: MisDefs.kvBlocks[i].1,
                             block: d.obj(MisDefs.kvBlocks[i].0),
                             order: payload.keyOrder[MisDefs.kvBlocks[i].0] ?? [])
            }
            ForEach(0..<MisDefs.tables.count, id: \.self) { i in
                MisTableSection(def: MisDefs.tables[i], rows: MisDefs.rows(d[MisDefs.tables[i].key]))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct MisHeaderCard: View {
    let d: [String: JSONValue]

    private var subtitle: String {
        var parts: [String] = []
        if let seg = d.str("segment"), !seg.isEmpty { parts.append("Segment \(seg)") }
        parts.append("Recovery base: \(d.str("base_label") ?? "ENR")")
        return parts.joined(separator: " · ")
    }

    var body: some View {
        InfoCard {
            Text("\(d.str("bank") ?? "—") · \(d.str("product") ?? "—")")
                .fontWeight(.bold).foregroundColor(.BrandBlue)
            Text(subtitle).font(.labelSmall).foregroundColor(.Muted)
        }
    }
}

private struct MisKvSection: View {
    let key: String
    let title: String
    let block: [String: JSONValue]
    let order: [String]

    /// Server order when known (Kotlin LinkedHashMap), else alphabetical.
    private var keys: [String] {
        var out: [String] = order.filter { block[$0] != nil }
        let rest: [String] = block.keys.filter { !out.contains($0) }.sorted()
        out.append(contentsOf: rest)
        return out
    }

    var body: some View {
        if !block.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                SectionTitle(title)
                InfoCard {
                    let ks: [String] = keys
                    ForEach(0..<ks.count, id: \.self) { i in
                        MisKvRow(k: ks[i], v: block[ks[i]])
                        if i < ks.count - 1 {
                            Divider().background(Color.MutedDim.opacity(0.15))
                        }
                    }
                }
            }
        }
    }
}

private struct MisKvRow: View {
    let k: String
    let v: JSONValue?

    var body: some View {
        HStack(alignment: .top) {
            Text(MisDefs.prettyKey(k)).font(.bodySmall).foregroundColor(.Muted)
            Spacer(minLength: 8)
            Text(MisDefs.fmtCell(k.contains("pct") ? "%" : MisDefs.prettyKey(k), v))
                .font(.bodySmall).fontWeight(.semibold).foregroundColor(.TextDark)
                .multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 3)
    }
}

private struct MisTableSection: View {
    let def: MisTableDef
    let rows: [[String: JSONValue]]

    var body: some View {
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                SectionTitle(def.title)
                if def.key == "trend" {
                    MisTrendChartCard(rows: rows)
                }
                MisTable(cols: def.cols, rows: rows)
            }
        }
    }
}

/// Horizontally scrollable grid: wide first column, fixed-width cells.
private struct MisTable: View {
    let cols: [MisCol]
    let rows: [[String: JSONValue]]

    private let firstW: CGFloat = 150
    private let cellW: CGFloat = 96

    private func width(_ i: Int) -> CGFloat { i == 0 ? firstW : cellW }

    var body: some View {
        InfoCard(spacing: 0, padding: 12) {
            ScrollView(.horizontal, showsIndicators: true) {
                VStack(alignment: .leading, spacing: 0) {
                    headerRow
                    Divider().background(Color.MutedDim.opacity(0.25))
                    ForEach(0..<rows.count, id: \.self) { r in
                        MisTableRow(cols: cols, row: rows[r], firstW: firstW, cellW: cellW)
                    }
                }
            }
        }
    }

    private var headerRow: some View {
        HStack(alignment: .bottom, spacing: 0) {
            ForEach(0..<cols.count, id: \.self) { i in
                Text(cols[i].header)
                    .font(.labelSmall).fontWeight(.bold).foregroundColor(.BrandBlue)
                    .frame(width: width(i) - 8, alignment: .leading)
                    .padding(.trailing, 8)
                    .padding(.bottom, 4)
            }
        }
    }
}

private struct MisTableRow: View {
    let cols: [MisCol]
    let row: [String: JSONValue]
    let firstW: CGFloat
    let cellW: CGFloat

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            ForEach(0..<cols.count, id: \.self) { i in
                Text(MisDefs.fmtCell(cols[i].header, row[cols[i].key]))
                    .font(.labelSmall)
                    .fontWeight(i == 0 ? .medium : .regular)
                    .foregroundColor(.TextDark)
                    .frame(width: (i == 0 ? firstW : cellW) - 8, alignment: .leading)
                    .padding(.trailing, 8)
            }
        }
        .padding(.vertical, 3)
    }
}

/// Line chart above the "Collection trend (30d)" table (Swift Charts).
private struct MisTrendChartCard: View {
    let rows: [[String: JSONValue]]

    private var points: [DashTrendItem] {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        var out: [DashTrendItem] = []
        for (i, r) in rows.enumerated() {
            let s: String = String((r.str("date") ?? "").prefix(10))
            if let date = f.date(from: s) {
                out.append(DashTrendItem(id: i, date: date, collected: r.dbl("collected") ?? 0))
            }
        }
        return out
    }

    var body: some View {
        let pts: [DashTrendItem] = points
        if pts.count >= 2 {
            InfoCard {
                DashTrendChart(points: pts)
            }
        }
    }
}
