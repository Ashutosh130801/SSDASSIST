import SwiftUI

// Port of RtsbScreen (ui/common/CollabScreens.kt) — target vs achievement.

private let RTSB_MONTHS: [(String, String)] = [("current", "This month"), ("next", "Next"), ("last", "Last"), ("all", "All")]
private let RTSB_ROLES: [(String, String)] = [("", "All"), ("caller", "Callers"), ("fos", "Field")]
private let RTSB_TABS: [(String, String)] = [("pending", "Not achieved"), ("achieved", "Achieved"), ("all", "All")]

private struct RtsbKey: Hashable {
    let mb: String
    let role: String
}

struct RtsbView: View {
    init() {}

    @State private var mb: String = "current"
    @State private var role: String = ""
    @State private var tab: String = "pending"

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("🎯 RTSB — target vs achievement")
                .font(.system(size: 18, weight: .bold)).foregroundColor(.TextDark)
            chipRow(RTSB_MONTHS, selected: mb) { mb = $0 }
            chipRow(RTSB_ROLES, selected: role) { role = $0 }
            AsyncContent(key: AnyHashable(RtsbKey(mb: mb, role: role)), load: {
                try await API.shared.rtsb(monthBucket: mb, role: role)
            }) { (d: [String: JSONValue], _: @escaping () -> Void) in
                RtsbBody(d: d, tab: $tab)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func chipRow(_ opts: [(String, String)], selected: String, _ pick: @escaping (String) -> Void) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(0..<opts.count, id: \.self) { i in
                    Chip(label: opts[i].1, selected: selected == opts[i].0) { pick(opts[i].0) }
                }
            }
        }
    }
}

private struct RtsbBody: View {
    let d: [String: JSONValue]
    @Binding var tab: String

    private var list: [JSONValue] {
        switch tab {
        case "achieved": return d["achieved_list"].cl
        case "all": return d["people"].cl
        default: return d["pending_list"].cl
        }
    }

    var body: some View {
        let t: [String: JSONValue] = d["totals"].cm
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                CollabKpi("People", String(t["people"].ci))
                CollabKpi("Achieved", String(t["achieved"].ci), .Good)
                CollabKpi("Not yet", String(t["pending"].ci), .Warn)
            }
            HStack(spacing: 6) {
                ForEach(0..<RTSB_TABS.count, id: \.self) { i in
                    Chip(label: RTSB_TABS[i].1, selected: tab == RTSB_TABS[i].0) { tab = RTSB_TABS[i].0 }
                }
            }
            ScrollView {
                LazyVStack(spacing: 6) {
                    let rows: [JSONValue] = list
                    ForEach(0..<rows.count, id: \.self) { i in
                        RtsbRow(p: rows[i].cm)
                    }
                }
                .padding(.bottom, 140)
            }
        }
    }
}

private struct RtsbRow: View {
    let p: [String: JSONValue]

    private var pctColor: Color {
        if p["achieved"].cTrue { return .Good }
        if p["pct_done"].cd >= 60 { return .Warn }
        return .Bad
    }

    private var subline: String {
        let who: String = p["role"].cs == "fos" ? "Field" : "Caller"
        return "\(who) · \(p["paid"].ci)/\(p["cases"].ci) paid · target \(inr(p["target_enr"].cd)) · "
            + "got \(inr(p["achieved_enr"].cd)) · gap \(inr(p["gap_enr"].cd))"
    }

    var body: some View {
        CollabCard {
            HStack {
                Text(p["name"].cs).fontWeight(.semibold).foregroundColor(.TextDark)
                Spacer()
                Text(collabPct(p["pct_done"].cd)).fontWeight(.bold).foregroundColor(pctColor)
            }
            Text(subline).font(.system(size: 12)).foregroundColor(.Muted)
        }
    }
}
