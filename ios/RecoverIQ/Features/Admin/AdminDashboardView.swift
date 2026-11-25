import SwiftUI

// Port of AdminScreens.kt AdminDashboardScreen — case-derived KPIs + the 15 highest-outstanding cases.
struct AdminDashboardView: View {
    @EnvironmentObject var app: AppState
    init() {}

    var body: some View {
        AsyncContent(key: AnyHashable("admin-dashboard"), live: true,
                     load: { try await API.shared.allCases() }) { cases, _ in
            AdminDashboardBody(cases: cases, roleLabel: app.user?.roleLabel ?? "",
                               onOpenCase: { id in
                                   // AppRoot pushes CaseDetailView on its NavigationStack.
                                   Realtime.shared.openCase.send(id)
                               })
        }
    }
}

private struct AdminDashboardBody: View {
    let cases: [Case]
    let roleLabel: String
    let onOpenCase: (Int) -> Void

    private var recovered: Double { cases.reduce(0.0) { $0 + $1.receivedAmount } }
    private var outstanding: Double { cases.reduce(0.0) { $0 + $1.pendingAmount } }
    private var resolved: Int {
        cases.filter { c in
            (c.status ?? "").lowercased() == "resolved" || (c.paidStatus ?? "").lowercased() == "paid"
        }.count
    }
    private var top: [Case] {
        Array(cases.sorted { $0.pendingAmount > $1.pendingAmount }.prefix(15))
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Dashboard").font(.headlineSmall).fontWeight(.bold).foregroundColor(.TextDark)
                    Text(roleLabel).font(.bodyMedium).foregroundColor(.Muted)
                }
                HStack(spacing: 12) {
                    AdminKpi(label: "Total cases", value: String(cases.count))
                    AdminKpi(label: "Resolved", value: String(resolved))
                }
                HStack(spacing: 12) {
                    AdminKpi(label: "Recovered", value: inr(recovered))
                    AdminKpi(label: "Outstanding", value: inr(outstanding))
                }
                SectionTitle("Highest outstanding")
                let list: [Case] = top
                ForEach(list) { c in
                    CaseCard(case: c, onClick: { onOpenCase(c.id) })
                }
            }
            .padding(16)
        }
    }
}

private struct AdminKpi: View {
    let label: String
    let value: String

    var body: some View {
        InfoCard {
            Text(value)
                .font(.headlineSmall).fontWeight(.bold).foregroundColor(.BrandBlue)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(label).font(.bodySmall).foregroundColor(.Muted)
        }
    }
}
