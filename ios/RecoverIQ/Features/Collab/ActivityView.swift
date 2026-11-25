import SwiftUI

// Port of ui/screens/ActivityScreen.kt — recent visits / calls / payments feed with a kind filter.

private let ACTIVITY_KINDS: [String] = ["all", "visits", "calls", "payments"]

private func capFirst(_ s: String) -> String {
    if s.isEmpty { return s }
    return s.prefix(1).uppercased() + String(s.dropFirst())
}

struct ActivityView: View {
    init() {}

    @State private var kind: String = "all"

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Activity")
                .padding(.top, 12).padding(.leading, 4)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(ACTIVITY_KINDS, id: \.self) { k in
                        Chip(label: capFirst(k), selected: kind == k) { kind = k }
                    }
                }
            }
            AsyncContent(key: AnyHashable(kind), load: { try await API.shared.activity(kind: kind) }) { (items: [ActivityItem], _: @escaping () -> Void) in
                if items.isEmpty {
                    EmptyState("No recent activity.")
                } else {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(0..<items.count, id: \.self) { i in
                                ActivityCard(a: items[i])
                            }
                        }
                        .padding(.top, 8)
                        .padding(.bottom, 140)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
    }
}

private struct ActivityCard: View {
    let a: ActivityItem

    private var color: Color {
        switch a.type {
        case "payment": return .Good
        case "visit": return .BrandBlue
        case "call": return .Warn
        default: return .Muted
        }
    }

    private var metaLine: String {
        var parts: [String] = []
        if let b = a.bank { parts.append(b) }
        if let by = a.by { parts.append("by \(by)") }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        InfoCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(capFirst(a.type)) · \(a.customer ?? "—")").fontWeight(.semibold).foregroundColor(color)
                    if let d = a.detail, !d.trimmingCharacters(in: .whitespaces).isEmpty {
                        Text(d).font(.bodySmall).foregroundColor(.Muted)
                    }
                    if let n = a.note, !n.trimmingCharacters(in: .whitespaces).isEmpty {
                        Text(n).font(.bodySmall).foregroundColor(.Muted)
                    }
                    Text(metaLine).font(.labelSmall).foregroundColor(.Muted)
                    if a.offLocation == true {
                        Text("⚠ Off-location visit").font(.labelSmall).foregroundColor(.Bad)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 2) {
                    if (a.amount ?? 0.0) > 0.0 {
                        Text(inr(a.amount ?? 0.0)).fontWeight(.bold).foregroundColor(.Good)
                    }
                    Text(DateUtil.humanTime(a.at)).font(.labelSmall).foregroundColor(.Muted)
                }
            }
        }
    }
}
