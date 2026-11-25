import SwiftUI

/// Port of ui/common/MyPerformanceScreen.kt — the signed-in FOS/caller's OWN scorecard: per-portfolio
/// achievement + the portfolio-wise leaderboard (peers on the same portfolio ranked by paid %, with the
/// viewer's row highlighted), kept separate per month.
struct MyPerformanceView: View {
    @State private var mb: String = "current"

    private let months: [ClrMonthOption] = [
        ClrMonthOption(value: "current", label: "This month"),
        ClrMonthOption(value: "next", label: "Next month"),
        ClrMonthOption(value: "", label: "All months"),
    ]

    init() {}

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("My Performance").padding(.top, 12).padding(.leading, 4)
            ClrMonthChips(options: months, selected: $mb)
            Text("Each portfolio is kept separate for the month you pick — nothing is merged.")
                .font(.labelSmall).foregroundColor(.Muted)
            AsyncContent(key: AnyHashable(mb), live: true,
                         load: { try await API.shared.myPerformance(monthBucket: mb) }) { d, _ in
                ScrollView {
                    MpPerformanceBody(d: d).padding(.bottom, 20)
                }
            }
        }
        .padding(.horizontal, 12)
    }
}

private struct MpPerformanceBody: View {
    let d: Performance

    private var roleWord: String { d.asFos ? "field agents" : "callers" }

    var body: some View {
        let t: PerfTotals = d.totals
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                ClrMetricBox(label: "My cases", value: String(t.count), sub: "\(t.paid) paid · \(t.unpaid) open",
                             valueFont: .titleMedium)
                ClrMetricBox(label: "My book (ENR)", value: inr(t.enr), valueFont: .titleMedium)
                ClrMetricBox(label: "Achieved", value: clrPct0(t.achievedPct) + "%", color: .Good,
                             sub: inr(t.paidEnr), valueFont: .titleMedium)
            }
            HStack(spacing: 8) {
                ClrMetricBox(label: "Cash collected", value: inr(t.collected), color: .Warn,
                             sub: "\(inr(t.pending)) pending", valueFont: .titleMedium)
                ClrMetricBox(label: "Total POS", value: inr(t.pos), sub: "principal outstanding", valueFont: .titleMedium)
                ClrMetricBox(label: "Pending", value: inr(t.pending), color: .Warn, valueFont: .titleMedium)
            }
            TrendStrip(trends: d.trends, title: "My cash collected — FTD / MTD / LMTD / Overall")
            if d.portfolios.isEmpty {
                Text("No portfolios assigned to you for this month yet.")
                    .foregroundColor(.Muted).padding(8)
            }
            ForEach(0..<d.portfolios.count, id: \.self) { i in
                MpPortfolioCard(p: d.portfolios[i], roleWord: roleWord)
            }
        }
    }
}

private struct MpPortfolioCard: View {
    let p: PerfPortfolio
    let roleWord: String

    private var line1: String {
        var s = "Cases \(p.count) · Paid \(p.paid)/\(p.count) · ENR \(inr(p.enr)) · Achieved \(clrPct0(p.achievedPct))%"
        if p.targetPct > 0 { s += " · Target \(clrPct0(p.targetPct))%" }
        return s
    }

    private var line2: String {
        return "Cash \(inr(p.collected)) · Pending \(inr(p.pending)) · POS \(inr(p.pos))"
    }

    private var line3: String {
        if roleWord == "field agents" {
            return "🧍 Visited \(p.activity.visited) · 💰 \(p.activity.visitsPaid) with payment"
        }
        return "📞 Contacted \(p.activity.contacted) · ☎️ \(p.activity.calls) calls"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center) {
                Text(p.label).fontWeight(.semibold).frame(maxWidth: .infinity, alignment: .leading)
                if let r = p.rank {
                    Text("🏆 #\(r)/\(p.fieldSize)")
                        .font(.labelMedium).fontWeight(.bold).foregroundColor(.BrandBlue)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(RoundedRectangle(cornerRadius: 8).fill(Color.BrandBlue.opacity(0.12)))
                }
            }
            Text(line1).font(.labelSmall).foregroundColor(.Muted).padding(.top, 6)
            Text(line2).font(.labelSmall).foregroundColor(.Muted).padding(.top, 2)
            Text(line3).font(.labelSmall).foregroundColor(.Muted).padding(.top, 2)
            if !p.leaderboard.isEmpty {
                Text("Leaderboard — \(roleWord) on this portfolio (you are highlighted)")
                    .font(.labelSmall).foregroundColor(.Muted).padding(.top, 10)
                MpLeaderHeader().padding(.top, 4)
                ForEach(0..<p.leaderboard.count, id: \.self) { i in
                    MpLeaderRowView(r: p.leaderboard[i])
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

/// One table cell with a proportional width (Compose RowScope.weight).
private struct MpLeaderCell: View {
    let text: String
    let weight: CGFloat
    let total: CGFloat
    var end: Bool = false
    var bold: Bool = false
    var color: Color = .TextDark

    var body: some View {
        Text(text)
            .font(.labelSmall)
            .fontWeight(bold ? .bold : .regular)
            .foregroundColor(color)
            .lineLimit(1).minimumScaleFactor(0.7)
            .frame(width: max(total * weight, 0), alignment: end ? .trailing : .leading)
    }
}

private struct MpLeaderHeader: View {
    var body: some View {
        GeometryReader { g in
            let w: CGFloat = g.size.width
            HStack(spacing: 0) {
                MpLeaderCell(text: "#", weight: 0.10, total: w)
                MpLeaderCell(text: "Agent", weight: 0.40, total: w)
                MpLeaderCell(text: "Cases", weight: 0.16, total: w, end: true)
                MpLeaderCell(text: "Paid %", weight: 0.16, total: w, end: true)
                MpLeaderCell(text: "Cash", weight: 0.18, total: w, end: true)
            }
        }
        .frame(height: 18)
        .padding(.vertical, 3)
    }
}

private struct MpLeaderRowView: View {
    let r: PerfLeaderRow

    private var pctColor: Color {
        if r.achievedPct >= 60 { return .Good }
        if r.achievedPct >= 30 { return .Warn }
        return .TextDark
    }

    var body: some View {
        GeometryReader { g in
            let w: CGFloat = g.size.width
            HStack(spacing: 0) {
                MpLeaderCell(text: String(r.rank), weight: 0.10, total: w, bold: r.you)
                MpLeaderCell(text: r.name + (r.you ? " (you)" : ""), weight: 0.40, total: w, bold: r.you)
                MpLeaderCell(text: String(r.count), weight: 0.16, total: w, end: true, bold: r.you)
                MpLeaderCell(text: clrPct0(r.achievedPct) + "%", weight: 0.16, total: w, end: true, bold: true, color: pctColor)
                MpLeaderCell(text: inr(r.collected), weight: 0.18, total: w, end: true, bold: r.you, color: .Good)
            }
            .frame(maxHeight: .infinity)
        }
        .frame(height: 18)
        .padding(.vertical, 4).padding(.horizontal, 2)
        .background(RoundedRectangle(cornerRadius: 6).fill(r.you ? Color.BrandBlue.opacity(0.12) : Color.clear))
    }
}
