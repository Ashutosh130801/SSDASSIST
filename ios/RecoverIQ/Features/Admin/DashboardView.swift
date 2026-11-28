import SwiftUI
import Charts

// Port of ui/admin/DashboardScreen.kt — "Dashboard" for managers / HO / admin and "My stats" for
// field agents (FOS) and tele-callers. GET /api/analytics/dashboard.
struct DashboardView: View {
    @EnvironmentObject var app: AppState

    init() {}

    var body: some View {
        if let user = app.user {
            AsyncContent(key: AnyHashable("dashboard|\(user.id)|\(user.role)"), live: true,
                         load: { try await API.shared.dashboard() }) { d, _ in
                DashboardBody(d: d, user: user)
            }
        } else {
            EmptyState(text: "Not signed in")
        }
    }
}

// MARK: - Body

private struct DashboardBody: View {
    let d: DashboardResponse
    let user: User

    private var isAgent: Bool { user.isFieldAgent || user.isTelecaller }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                header
                if user.isFieldAgent {
                    FosOnDutyCard()   // shared with the FOS home (Features/Fos/FieldAgentTrackingView.swift)
                }
                kpiRows
                CollectionProgressCard(k: d.kpis)
                if isAgent {
                    MyTrendsCard()
                }
                pipelineSection
                trendSection
                dispositionSection
                bankSection
                leaderSection
            }
            .padding(16)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(isAgent ? "My stats" : "Dashboard")
                .font(.headlineSmall).fontWeight(.bold).foregroundColor(.TextDark)
            Text(user.roleLabel + (user.branch.map { " · \($0)" } ?? ""))
                .font(.bodyMedium).foregroundColor(.Muted)
        }
    }

    @ViewBuilder private var kpiRows: some View {
        HStack(spacing: 12) {
            DashKpi(label: "Cases", value: String(d.kpis.totalCases), color: .BrandBlue)
            DashKpi(label: "Recovery", value: String(format: "%.0f%%", d.kpis.recoveryRate), color: .BrandBlue)
        }
        HStack(spacing: 12) {
            DashKpi(label: "Received", value: inr(d.kpis.received), color: .Good)
            DashKpi(label: "Pending", value: inr(d.kpis.pending), color: .BrandBlue)
        }
        // Callers / field agents: actual cash collected front and centre on My Stats.
        if isAgent {
            HStack(spacing: 12) {
                DashKpi(label: "Cash collected", value: inr(d.kpis.cashCollected), color: .Good)
                DashKpi(label: "Resolved", value: String(d.kpis.paid), color: .Good)
            }
        }
    }

    /// Derived funnel (assigned/touched/ptp/paid); falls back to by_status for older backends.
    private var pipeItems: [DashBarItem] {
        var out: [DashBarItem] = []
        if !d.pipeline.isEmpty {
            for (i, p) in d.pipeline.enumerated() {
                let lbl: String = DASH_PIPELINE_LABELS[p.key] ?? ""
                out.append(DashBarItem(id: i, label: lbl.isEmpty ? p.key : lbl, count: p.count))
            }
        } else {
            for (i, s) in d.byStatus.enumerated() {
                out.append(DashBarItem(id: i, label: DASH_PIPELINE_LABELS[s.status] ?? s.status, count: s.count))
            }
        }
        return out
    }

    @ViewBuilder private var pipelineSection: some View {
        let items: [DashBarItem] = pipeItems
        if items.contains(where: { $0.count > 0 }) {
            SectionTitle("Collections pipeline")
            InfoCard {
                DashBarChart(items: items, color: .BrandBlue)
            }
        }
    }

    @ViewBuilder private var trendSection: some View {
        let pts: [DashTrendItem] = DashTrendItem.from(d.trend)
        if pts.count >= 2 {
            SectionTitle("Collection trend")
            InfoCard {
                DashTrendChart(points: pts)
            }
        }
    }

    private var dispItems: [DashBarItem] {
        var items: [DashBarItem] = []
        for (i, r) in d.byDisposition.enumerated() {
            items.append(DashBarItem(id: i, label: r.disposition, count: r.count))
        }
        return items
    }

    @ViewBuilder private var dispositionSection: some View {
        let items: [DashBarItem] = dispItems
        if items.contains(where: { $0.count > 0 }) {
            SectionTitle("Dispositions")
            InfoCard {
                DashBarChart(items: items, color: .Warn)
            }
        }
    }

    @ViewBuilder private var bankSection: some View {
        if !d.byBank.isEmpty {
            SectionTitle("By bank")
            ForEach(0..<d.byBank.count, id: \.self) { i in
                BankRowCard(b: d.byBank[i])
            }
        }
    }

    @ViewBuilder private var leaderSection: some View {
        if !d.leaderboard.isEmpty {
            SectionTitle("Field leaderboard")
            ForEach(0..<d.leaderboard.count, id: \.self) { i in
                LeaderRowCard(rank: i + 1, l: d.leaderboard[i])
            }
        }
    }
}

private let DASH_PIPELINE_LABELS: [String: String] = [
    "new": "New", "allocated": "Allocated", "in_progress": "In Progress",
    "ptp": "PTP", "paid": "Resolved", "unpaid": "Unpaid",
]

// MARK: - Small cards

private struct DashKpi: View {
    let label: String
    let value: String
    var color: Color = .BrandBlue

    var body: some View {
        InfoCard {
            Text(value)
                .font(.headlineSmall).fontWeight(.bold).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(label).font(.bodySmall).foregroundColor(.Muted)
        }
    }
}

private struct DashPill: View {
    let label: String
    let count: Int
    let color: Color

    var body: some View {
        VStack(spacing: 1) {
            Text(String(count)).fontWeight(.bold).foregroundColor(color)
            Text(label).font(.labelSmall).foregroundColor(.MutedDim)
        }
    }
}

private struct CollectionProgressCard: View {
    let k: DashboardKpis

    private var frac: Double {
        if k.target <= 0 { return 0 }
        return min(max(k.received / k.target, 0), 1)
    }

    var body: some View {
        InfoCard {
            Text("Collection progress").fontWeight(.semibold).foregroundColor(.TextDark)
            Text("\(inr(k.received)) of \(inr(k.target)) target")
                .font(.bodySmall).foregroundColor(.Muted)
            ProgressView(value: frac)
                .tint(.BrandBlue)
                .scaleEffect(x: 1, y: 2, anchor: .center)
                .padding(.top, 8)
            HStack {
                DashPill(label: "Paid", count: k.paid, color: .Good)
                Spacer()
                DashPill(label: "Partial", count: k.partial, color: .BrandBlue)
                Spacer()
                DashPill(label: "Unpaid", count: k.unpaid, color: .Muted)
            }
            .padding(.top, 8)
        }
    }
}

/// FOS / caller: FTD / MTD / LMTD / Overall cash collected (silently hidden on failure).
private struct MyTrendsCard: View {
    @State private var trends: Trends? = nil

    var body: some View {
        VStack(spacing: 0) {
            if let t = trends {
                InfoCard { TrendStrip(trends: t, title: "Cash collected — FTD / MTD / LMTD / Overall") }
            }
        }
        .task {
            if let r = try? await API.shared.myTrends() { trends = r.trends }
        }
    }
}

private struct BankRowCard: View {
    let b: BankRow

    var body: some View {
        InfoCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(b.bank).fontWeight(.semibold).foregroundColor(.TextDark)
                    Text("\(b.cases) cases").font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(inr(b.received)).fontWeight(.medium).foregroundColor(.Good)
                    Text("pending \(inr(b.pending))").font(.labelSmall).foregroundColor(.MutedDim)
                }
            }
        }
    }
}

private struct LeaderRowCard: View {
    let rank: Int
    let l: LeaderRow

    var body: some View {
        InfoCard {
            HStack(spacing: 12) {
                Text("#\(rank)").fontWeight(.bold).foregroundColor(.BrandBlue).frame(minWidth: 28, alignment: .leading)
                VStack(alignment: .leading, spacing: 2) {
                    Text(l.name).fontWeight(.semibold).foregroundColor(.TextDark)
                    Text("\(l.visits) visits").font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer()
                Text(inr(l.collected)).fontWeight(.medium).foregroundColor(.Good)
            }
        }
    }
}

// MARK: - Charts

struct DashBarItem: Identifiable {
    let id: Int
    let label: String
    let count: Int
}

/// Horizontal bar chart (pipeline / dispositions) — replaces the Kotlin LinearProgressIndicator rows.
struct DashBarChart: View {
    let items: [DashBarItem]
    var color: Color = .BrandBlue

    var body: some View {
        Chart(items) { item in
            BarMark(x: .value("Count", item.count),
                    y: .value("Stage", "\(item.id + 1). \(item.label)"))
                .foregroundStyle(color)
                .cornerRadius(4)
                .annotation(position: .trailing, alignment: .leading) {
                    Text(String(item.count))
                        .font(.labelSmall)
                        .foregroundColor(color)
                }
        }
        .chartYAxis {
            AxisMarks { value in
                AxisValueLabel {
                    Text(DashBarChart.stripIndex(value.as(String.self) ?? ""))
                        .font(.bodySmall)
                        .foregroundColor(.Muted)
                }
            }
        }
        .chartXAxis(.hidden)
        .frame(height: CGFloat(items.count) * 30 + 12)
    }

    /// The y value carries an index prefix so duplicate labels don't merge; hide it in the axis.
    static func stripIndex(_ s: String) -> String {
        if let r = s.range(of: ". ") { return String(s[r.upperBound...]) }
        return s
    }
}

struct DashTrendItem: Identifiable {
    let id: Int
    let date: Date
    let collected: Double

    static func from(_ pts: [TrendPoint]) -> [DashTrendItem] {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        var out: [DashTrendItem] = []
        for (i, p) in pts.enumerated() {
            let s: String = String(p.date.prefix(10))
            if let d = f.date(from: s) {
                out.append(DashTrendItem(id: i, date: d, collected: p.collected))
            }
        }
        return out
    }
}

/// Collection trend line (₹ collected per day).
struct DashTrendChart: View {
    let points: [DashTrendItem]

    var body: some View {
        Chart(points) { p in
            AreaMark(x: .value("Date", p.date, unit: .day), y: .value("Collected", p.collected))
                .foregroundStyle(Color.Good.opacity(0.15))
            LineMark(x: .value("Date", p.date, unit: .day), y: .value("Collected", p.collected))
                .foregroundStyle(Color.Good)
                .interpolationMethod(.monotone)
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine()
                AxisValueLabel {
                    Text(DashTrendChart.short(value.as(Double.self) ?? 0))
                        .font(.labelSmall)
                }
            }
        }
        .frame(height: 180)
    }

    static func short(_ v: Double) -> String {
        return inr(v)   // full amount, no K / L / Cr
    }
}
