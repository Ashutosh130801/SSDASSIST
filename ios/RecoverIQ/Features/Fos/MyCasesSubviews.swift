import SwiftUI

// Subviews for MyCasesView (keeps each body small for the type-checker).

// MARK: - PTP reminders banner (Kotlin RemindersBanner)

struct MyCasesRemindersBanner: View {
    let data: RemindersResponse?
    let onOpenCase: (Int) -> Void

    var body: some View {
        if let d = data, d.count != 0 {
            InfoCard(spacing: 2, padding: 12) {
                Text("🔔 PTP reminders · \(d.count)").fontWeight(.semibold).foregroundColor(.TextDark)
                Text("\(d.overdue) overdue · \(d.dueToday) due today")
                    .font(.labelSmall).foregroundColor(.Muted)
                    .padding(.bottom, 4)
                ForEach(Array(d.rows.prefix(6).enumerated()), id: \.offset) { pair in
                    reminderRow(pair.element)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func reminderRow(_ r: ReminderItem) -> some View {
        Button(action: { onOpenCase(r.caseId) }) {
            HStack(alignment: .center) {
                Text(r.customer ?? r.account ?? "Case")
                    .font(.bodySmall).foregroundColor(.TextDark)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.trailing, 8)
                Text((r.overdue ? "⚠ " : "") + (r.ptpDate ?? ""))
                    .font(.labelSmall)
                    .foregroundColor(r.overdue ? Color.Bad : Color.Warn)
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Month chips

struct MyCasesMonthChips: View {
    let months: [String]
    let cases: [Case]
    let current: String
    let onPick: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Text("Month:").foregroundColor(.Muted).padding(.trailing, 2)
                ForEach(months, id: \.self) { m in
                    Chip(label: "\(FosCaseLogic.monthLabel(m)) (\(count(m)))", selected: current == m) {
                        onPick(m)
                    }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
    }

    private func count(_ m: String) -> Int {
        return cases.filter { FosCaseLogic.monthOf($0) == m }.count
    }
}

// MARK: - Search field (OutlinedTextField with search icon)

struct FosSearchField: View {
    @Binding var text: String
    let placeholder: String
    let showClear: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(.Muted)
            TextField(placeholder, text: $text)
                .foregroundColor(.TextDark)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
            if showClear && !text.isEmpty {
                Button("✕") { text = "" }.foregroundColor(.BrandBlue)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.Muted.opacity(0.6), lineWidth: 1))
    }
}

// MARK: - Area search hit

struct MyCasesAreaHitRow: View {
    let c: Case
    let onOpen: () -> Void

    private var caption: String {
        let pins: [String] = FosCaseLogic.pinsOf(c)
        let pinText: String = pins.isEmpty ? "" : "  ·  PIN \(pins.joined(separator: ", "))"
        return "\(c.bank ?? "—") · \(c.product ?? "—")" + pinText
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(caption).font(.labelSmall).foregroundColor(.Muted)
            CaseCard(case: c, onClick: onOpen)
        }
    }
}

// MARK: - Portfolio card

struct MyCasesPortfolioCard: View {
    let portfolio: FosPortfolio
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            InfoCard(padding: 14) {
                HStack(alignment: .center) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(portfolio.bank)  ·  \(portfolio.product)")
                            .fontWeight(.bold).foregroundColor(.BrandBlue)
                        Text("\(portfolio.cases.count) account\(FosCaseLogic.plural(portfolio.cases.count))  ·  pending \(inr(portfolio.pending))")
                            .font(.bodySmall).foregroundColor(.Muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Text("›").fontWeight(.bold).foregroundColor(.Muted)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Portfolio context bar (back link, count, Excel / PDF)

struct MyCasesContextBar: View {
    let bank: String
    let product: String
    let count: Int
    let busy: Bool
    let onBack: () -> Void
    let onExport: (String) -> Void

    var body: some View {
        FlowLayout(spacing: 6, lineSpacing: 6) {
            Button(action: onBack) {
                Text("‹ \(bank)·\(product)").fontWeight(.semibold).foregroundColor(.BrandBlue)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 4).padding(.vertical, 6)
            Text("\(count)").foregroundColor(.Muted).padding(.vertical, 6).padding(.trailing, 6)
            exportButton("⬇ Excel", fmt: "xlsx")
            exportButton("⬇ PDF", fmt: "pdf")
            if busy { ProgressView().padding(.vertical, 6) }
        }
    }

    private func exportButton(_ label: String, fmt: String) -> some View {
        Button(action: { onExport(fmt) }) {
            Text(label).font(.labelLarge).foregroundColor(.BrandBlue)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .overlay(Capsule().stroke(Color.Muted.opacity(0.5), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(busy || count == 0)
    }
}

// MARK: - PIN chips

struct MyCasesPinChips: View {
    let pins: [FosPinCount]
    let selected: String?
    let onPick: (String?) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Text("PIN:").foregroundColor(.Muted).padding(.trailing, 2)
                Chip(label: "All", selected: selected == nil) { onPick(nil) }
                ForEach(pins) { p in
                    Chip(label: "\(p.pin) (\(p.count))", selected: selected == p.pin) {
                        onPick(selected == p.pin ? nil : p.pin)
                    }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
    }
}

// MARK: - Status filter chips

struct MyCasesFilterChips: View {
    let portCases: [Case]
    let selected: String
    let onPick: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(FosCaseLogic.filters, id: \.label) { f in
                    Chip(label: "\(f.label) (\(portCases.filter(f.test).count))", selected: selected == f.label) {
                        onPick(f.label)
                    }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
    }
}

// MARK: - Sort chips

struct MyCasesSortChips: View {
    let selected: String
    let onPick: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Text("Sort:").foregroundColor(.Muted).padding(.trailing, 2)
                ForEach(FosCaseLogic.sorts, id: \.label) { s in
                    Chip(label: s.label, selected: selected == s.label) { onPick(s.label) }
                }
            }
            .padding(.horizontal, 16)
        }
    }
}
