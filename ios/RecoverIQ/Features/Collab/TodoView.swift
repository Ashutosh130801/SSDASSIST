import SwiftUI

// Port of TodoScreen (ui/common/CollabScreens.kt) — "My work queue — today".

private struct TodoSection {
    let key: String
    let label: String
    let color: Color
}

struct TodoView: View {
    var onOpenCase: (Int) -> Void

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    @EnvironmentObject var app: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("📋 My work queue — today")
                .font(.system(size: 18, weight: .bold)).foregroundColor(.TextDark)
            AsyncContent(load: { try await API.shared.todoMe() }) { (d: [String: JSONValue], _: @escaping () -> Void) in
                TodoBody(d: d, isFos: (app.user?.role ?? "") == "fos", onOpenCase: onOpenCase)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

private struct TodoBody: View {
    let d: [String: JSONValue]
    let isFos: Bool
    let onOpenCase: (Int) -> Void

    private var sections: [TodoSection] {
        let middle: TodoSection = isFos
            ? TodoSection(key: "visits_pending", label: "📍 Visits pending", color: .BrandBlue)
            : TodoSection(key: "calls_pending", label: "📞 Calls pending", color: .BrandBlue)
        return [
            TodoSection(key: "ptp_broken", label: "🔴 Broken PTPs (overdue)", color: .Bad),
            TodoSection(key: "ptp_today", label: "🤝 Today's PTPs", color: .Warn),
            middle,
            TodoSection(key: "paid_not_updated", label: "💰 Paid — status not updated", color: .Good),
        ]
    }

    var body: some View {
        let callbacks: [JSONValue] = d["callbacks"].cl
        let secs: [TodoSection] = sections
        ScrollView {
            LazyVStack(spacing: 8) {
                if !callbacks.isEmpty {
                    CallbacksCard(callbacks: callbacks, onOpenCase: onOpenCase)
                }
                ForEach(0..<secs.count, id: \.self) { i in
                    TodoSectionCard(section: secs[i], rows: d[secs[i].key].cl, onOpenCase: onOpenCase)
                }
            }
            .padding(.bottom, 140)
        }
    }
}

private struct CallbacksCard: View {
    let callbacks: [JSONValue]
    let onOpenCase: (Int) -> Void

    var body: some View {
        CollabCard {
            Text("📞 Callback requests (\(callbacks.count))").fontWeight(.bold).foregroundColor(.BrandBlue)
            ForEach(0..<callbacks.count, id: \.self) { i in
                let c: [String: JSONValue] = callbacks[i].cm
                Text("\(c["from"].cs) · \(c["body"].cs)")
                    .font(.system(size: 12)).foregroundColor(.TextDark)
                    .padding(.top, 3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if let id = c["case_id"].cNum { onOpenCase(id) }
                    }
            }
        }
    }
}

private struct TodoSectionCard: View {
    let section: TodoSection
    let rows: [JSONValue]
    let onOpenCase: (Int) -> Void

    var body: some View {
        CollabCard {
            Text("\(section.label) · \(rows.count)").fontWeight(.semibold).foregroundColor(section.color)
            if rows.isEmpty {
                Text("Nothing pending 🎉").font(.system(size: 12)).foregroundColor(.Muted)
            } else {
                let shown: [JSONValue] = Array(rows.prefix(40))
                ForEach(0..<shown.count, id: \.self) { i in
                    TodoRow(c: shown[i].cm, onOpenCase: onOpenCase)
                }
            }
        }
    }
}

private struct TodoRow: View {
    let c: [String: JSONValue]
    let onOpenCase: (Int) -> Void

    private var title: String {
        let cust: String = c["customer"].cs
        return cust.trimmingCharacters(in: .whitespaces).isEmpty ? c["account"].cs : cust
    }

    private var sub: String {
        var s: String = "\(c["bank"].cs) \(c["product"].cs) · pending \(inr(c["pending"].cd))"
        if let f = c["follow_up"], !f.isNull { s += " · due \(f.text)" }
        return s
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title).font(.system(size: 13, weight: .medium)).foregroundColor(.TextDark)
            Text(sub).font(.system(size: 11)).foregroundColor(.Muted)
        }
        .padding(.top, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture {
            if let id = c["id"].cNum { onOpenCase(id) }
        }
    }
}
