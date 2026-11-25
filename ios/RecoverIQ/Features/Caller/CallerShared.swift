import SwiftUI

// Small helpers shared by the Caller / Team Lead / Portfolio screens (prefixed `Clr` to avoid
// clashing with other feature groups).

/// One option of a month-bucket chip row: (value sent to the API, label).
struct ClrMonthOption: Hashable {
    let value: String
    let label: String
}

/// Horizontal row of single-select month chips.
struct ClrMonthChips: View {
    let options: [ClrMonthOption]
    @Binding var selected: String
    var leading: String? = nil

    init(options: [ClrMonthOption], selected: Binding<String>, leading: String? = nil) {
        self.options = options
        self._selected = selected
        self.leading = leading
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if let l = leading {
                    Text(l).font(.labelSmall).foregroundColor(.Muted)
                }
                ForEach(options, id: \.self) { o in
                    Chip(label: o.label, selected: selected == o.value) { selected = o.value }
                }
            }
        }
    }
}

/// Rounded search text field with a magnifier (Compose OutlinedTextField + Search icon).
struct ClrSearchField: View {
    let placeholder: String
    @Binding var text: String

    init(_ placeholder: String, text: Binding<String>) {
        self.placeholder = placeholder
        self._text = text
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(.Muted)
            TextField(placeholder, text: $text)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
            if !text.isEmpty {
                Button(action: { text = "" }) {
                    Image(systemName: "xmark.circle.fill").foregroundColor(.MutedDim)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.StrokeSoft, lineWidth: 1))
    }
}

/// Bordered small metric box (Kotlin `Metric` / `Kpi` Surface).
struct ClrMetricBox: View {
    let label: String
    let value: String
    var color: Color = .TextDark
    var sub: String? = nil
    var valueFont: Font = .titleSmall

    init(label: String, value: String, color: Color = .TextDark, sub: String? = nil, valueFont: Font = .titleSmall) {
        self.label = label
        self.value = value
        self.color = color
        self.sub = sub
        self.valueFont = valueFont
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.labelSmall).foregroundColor(.Muted).lineLimit(1)
            Text(value).font(valueFont).fontWeight(.semibold).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.6)
            if let s = sub {
                Text(s).font(.labelSmall).foregroundColor(.Muted).lineLimit(2)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

/// "%.0f" helper.
func clrPct0(_ v: Double) -> String { String(format: "%.0f", v) }

/// Identifiable target for the person-performance sheet.
struct ClrPerfTarget: Identifiable, Hashable {
    let empId: Int
    let role: String
    var id: String { "\(empId)|\(role)" }
}

/// Port of PortfolioScreen.kt `PerformanceDialog` — a person's scorecard (opened from FOS/caller chips).
struct ClrPerformanceSheet: View {
    let empId: Int
    let role: String
    let onDismiss: () -> Void

    @State private var mb: String = "current"

    private let months: [ClrMonthOption] = [
        ClrMonthOption(value: "current", label: "This month"),
        ClrMonthOption(value: "next", label: "Next"),
        ClrMonthOption(value: "", label: "All"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Performance").font(.titleMedium).fontWeight(.bold)
                Spacer()
                Button("Close", action: onDismiss)
            }
            ClrMonthChips(options: months, selected: $mb)
            AsyncContent(key: AnyHashable("\(empId)|\(role)|\(mb)"),
                         load: { try await API.shared.performance(empId: empId, role: role, monthBucket: mb) }) { d, _ in
                ScrollView {
                    ClrPerformanceBody(d: d).padding(.bottom, 16)
                }
            }
        }
        .padding(16)
        .background(Color.CardWhite.ignoresSafeArea())
    }
}

private struct ClrPerformanceBody: View {
    let d: Performance

    private var title: String {
        var parts: [String] = []
        if let n = d.name { parts.append(n) }
        if let c = d.empCode { parts.append("(\(c))") }
        parts.append(d.asFos ? "FOS" : "Caller")
        return parts.joined(separator: " ")
    }

    private var activityLine: String {
        if d.asFos {
            return "🧍 Visited \(d.activity.visited) cases · 📋 \(d.activity.visits) visits · 💰 \(d.activity.visitsPaid) with payment"
        }
        return "📞 Contacted \(d.activity.contacted) cases · ☎️ \(d.activity.calls) calls logged"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).fontWeight(.semibold)
            HStack(spacing: 8) {
                ClrMetricBox(label: "Cases", value: String(d.totals.count))
                ClrMetricBox(label: "Collected", value: inr(d.totals.collected), color: .Good)
                ClrMetricBox(label: "Achieved", value: clrPct0(d.totals.achievedPct) + "%", color: .BrandBlue)
            }
            HStack(spacing: 8) {
                ClrMetricBox(label: "Pending", value: inr(d.totals.pending), color: .Warn)
                ClrMetricBox(label: "Total POS", value: inr(d.totals.pos))
                Color.clear.frame(maxWidth: .infinity, maxHeight: 1)
            }
            Text(activityLine).font(.bodySmall).foregroundColor(.Muted)
            if d.activity.collected > 0 {
                Text("💵 Collected (call+visit logs): \(inr(d.activity.collected))")
                    .font(.bodySmall).fontWeight(.semibold).foregroundColor(.Good)
            }
            TrendStrip(trends: d.trends, title: "Cash collected — FTD / MTD / LMTD / Overall")
            ForEach(0..<d.portfolios.count, id: \.self) { i in
                ClrPerfPortfolioRow(p: d.portfolios[i], asFos: d.asFos)
            }
            if d.portfolios.isEmpty {
                Text("No cases in this period.").foregroundColor(.Muted)
            }
        }
    }
}

private struct ClrPerfPortfolioRow: View {
    let p: PerfPortfolio
    let asFos: Bool

    private var line: String {
        var s = "Paid \(p.paid)/\(p.count) · ENR \(inr(p.enr)) · Collected \(inr(p.collected)) · \(clrPct0(p.achievedPct))% · POS \(inr(p.pos))"
        if let r = p.rank { s += " · Rank #\(r)/\(p.fieldSize)" }
        return s
    }

    private var activity: String {
        if asFos { return "🧍 Visited \(p.activity.visited) · 💰 \(p.activity.visitsPaid) with payment" }
        return "📞 Contacted \(p.activity.contacted) · ☎️ \(p.activity.calls) calls"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(p.label).fontWeight(.semibold)
                Spacer()
                Text("\(p.count)").foregroundColor(.Muted)
            }
            Text(line).font(.labelSmall).foregroundColor(.Muted).padding(.top, 2)
            Text(activity).font(.labelSmall).foregroundColor(.Muted)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.GlassStroke, lineWidth: 1))
    }
}
