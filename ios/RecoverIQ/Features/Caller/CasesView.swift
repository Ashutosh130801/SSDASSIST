import SwiftUI

/// Port of ui/common/SharedScreens.kt `CasesScreen` — all cases with server-side search + status filter.
struct CasesView: View {
    var onOpenCase: (Int) -> Void

    @State private var search: String = ""
    @State private var status: String = "All"

    private let statusFilters: [String] = ["All", "new", "ptp", "callback", "paid"]

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("All cases").padding(.top, 12).padding(.leading, 4)
            ClrSearchField("Search name, account, phone, pincode", text: $search)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(statusFilters, id: \.self) { opt in
                        Chip(label: opt.prefix(1).uppercased() + String(opt.dropFirst()), selected: status == opt) {
                            status = opt
                        }
                    }
                }
            }
            .padding(.top, 8)
            AsyncContent(key: AnyHashable("\(search)|\(status)"), load: {
                try await API.shared.allCases(status: status == "All" ? nil : status, search: search)
            }) { cases, _ in
                ClrCasesResults(cases: cases, onOpenCase: onOpenCase)
            }
            .padding(.top, 8)
        }
        .padding(.horizontal, 12)
    }
}

private struct ClrCasesResults: View {
    let cases: [Case]
    let onOpenCase: (Int) -> Void

    var body: some View {
        if cases.isEmpty {
            EmptyState(text: "No matching cases.")
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(cases) { c in
                        CaseCard(case: c, onClick: { onOpenCase(c.id) })
                    }
                }
                .padding(.bottom, 16)
            }
        }
    }
}
