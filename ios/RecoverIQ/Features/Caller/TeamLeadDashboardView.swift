import SwiftUI

/// Port of ui/teamlead/TeamLeadScreen.kt `TeamLeadDashboardScreen` — month chips, team KPIs and a card
/// per member (today's activity, FTD/MTD/LMTD/Overall trend strip, call button).
struct TeamLeadDashboardView: View {
    var onOpenCase: (Int) -> Void

    // This/Last/Next/All month — the whole team dashboard (KPIs, member cards, trend) follows it.
    @State private var monthB: String = "current"

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    var body: some View {
        AsyncContent(key: AnyHashable(monthB), live: true,
                     load: { try await API.shared.teamOverview(monthBucket: monthB) }) { ov, _ in
            TeamLeadBody(ov: ov, monthB: $monthB)
        }
    }
}

private struct TeamLeadBody: View {
    let ov: TeamOverview
    @Binding var monthB: String

    private let months: [ClrMonthOption] = [
        ClrMonthOption(value: "current", label: "This month"),
        ClrMonthOption(value: "next", label: "Next"),
        ClrMonthOption(value: "last", label: "Last"),
        ClrMonthOption(value: "all", label: "All"),
    ]

    private var header: String {
        return "My team" + (ov.lead?.branch.map { " · \($0)" } ?? "")
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                Text(header).font(.headlineSmall).fontWeight(.bold).foregroundColor(.TextDark)
                ClrMonthChips(options: months, selected: $monthB)
                kpiRows
                SectionTitle("Members")
                if ov.members.isEmpty {
                    EmptyState(text: "No team members yet.")
                } else {
                    ForEach(ov.members) { m in
                        TeamLeadMemberCard(m: m)
                    }
                }
            }
            .padding(16)
        }
    }

    private var kpiRows: some View {
        let k: TeamKpis = ov.kpis
        return VStack(spacing: 10) {
            HStack(spacing: 10) {
                TeamLeadKpi(label: "Members", value: "\(k.members)", sub: "\(k.fos) FOS · \(k.callers) callers")
                TeamLeadKpi(label: "Cases", value: "\(k.cases)", sub: "\(k.resolved) resolved")
            }
            HStack(spacing: 10) {
                TeamLeadKpi(label: "Recovered", value: inr(k.recovered), sub: nil, color: .Good)
                TeamLeadKpi(label: "Pending", value: inr(k.pending), sub: nil, color: .Warn)
                TeamLeadKpi(label: "Recovery", value: String(format: "%.1f%%", k.recoveryPct), sub: nil)
            }
        }
    }
}

private struct TeamLeadKpi: View {
    let label: String
    let value: String
    let sub: String?
    var color: Color = .BrandBlue

    var body: some View {
        InfoCard {
            Text(value).font(.titleLarge).fontWeight(.bold).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(label).font(.labelSmall).foregroundColor(.Muted)
            if let s = sub {
                Text(s).font(.labelSmall).foregroundColor(.Muted)
            }
        }
    }
}

private func teamRoleLabel(_ r: String) -> String {
    switch r {
    case "fos": return "Field Agent"
    case "telecaller": return "Tele-calling Agent"
    default: return r.prefix(1).uppercased() + String(r.dropFirst())
    }
}

private struct TeamLeadMemberCard: View {
    let m: TeamMemberCard

    @State private var trends: Trends? = nil

    private var subLine: String {
        var s: String = teamRoleLabel(m.role)
        if let code = m.empCode { s += " · " + code }
        if let ph = m.phone { s += " · " + ph }
        return s
    }

    private var firstName: String {
        return String(m.name.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: false).first ?? Substring(m.name))
    }

    var body: some View {
        InfoCard {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(m.name).font(.titleSmall).fontWeight(.semibold)
                    Text(subLine).font(.labelSmall).foregroundColor(.Muted)
                }
                Spacer()
                Text(clrPct0(m.recoveryPct) + "%").fontWeight(.bold).foregroundColor(.BrandBlue)
            }
            HStack(spacing: 12) {
                Text("Cases \(m.assigned)").font(.labelSmall).foregroundColor(.Muted)
                Text("Resolved \(m.resolved)").font(.labelSmall).foregroundColor(.Good)
                Text("Recovered \(inr(m.recovered))").font(.labelSmall).foregroundColor(.Good)
            }
            .padding(.top, 6)
            if let t = m.today {
                Text(todayLine(t)).font(.labelSmall).foregroundColor(.Muted)
            }
            if let t = trends {
                TrendStrip(trends: t, title: "Cash collected — FTD / MTD / LMTD / Overall")
                    .padding(.top, 8)
            }
            if let p = m.phone, !p.trimmingCharacters(in: .whitespaces).isEmpty {
                Button(action: { Actions.dial(p) }) {
                    Label("Call \(firstName)", systemImage: "phone.fill")
                        .font(.system(size: 14, weight: .medium))
                }
                .buttonStyle(.bordered)
                .tint(.BrandBlue)
                .padding(.top, 8)
            }
        }
        .task(id: m.id) {
            // FTD / MTD / LMTD / Overall achievement for this team member.
            trends = try? await API.shared.employeeTrends(userId: m.id).trends
        }
    }

    private func todayLine(_ t: MemberToday) -> String {
        if t.label == "visits" { return "\(t.count) visits today" }
        return "\(t.count) calls today · \(t.ptp ?? 0) PTP"
    }
}
