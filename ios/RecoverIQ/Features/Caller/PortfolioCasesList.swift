import SwiftUI

/// Port of PortfolioScreen.kt `PortfolioCases` — search + paid/cycle/FOS/caller multi-select filters
/// over one product (+ optional branch) and the matching case list.
struct PortfolioCasesList: View {
    let p: ProductSummary
    let branch: String?
    let onOpenCase: (Int) -> Void
    let onOpenPerf: (Int, String) -> Void

    @State private var paid: String? = nil
    @State private var cycles: Set<String> = []
    @State private var fos: Set<Int> = []
    @State private var callers: Set<Int> = []
    @State private var q: String = ""
    @State private var opts: FilterOptions = FilterOptions()

    private let paidOptions: [String?] = [nil, "PAID", "UNPAID", "PARTIAL"]

    init(p: ProductSummary, branch: String?, onOpenCase: @escaping (Int) -> Void,
         onOpenPerf: @escaping (Int, String) -> Void) {
        self.p = p
        self.branch = branch
        self.onOpenCase = onOpenCase
        self.onOpenPerf = onOpenPerf
    }

    private var optsKey: String { "\(p.bank)|\(p.product)|\(branch ?? "null")" }

    private var casesKey: String {
        let cy: String = cycles.sorted().joined(separator: ",")
        let fo: String = fos.sorted().map { String($0) }.joined(separator: ",")
        let ca: String = callers.sorted().map { String($0) }.joined(separator: ",")
        return "\(p.bank)|\(p.product)|\(branch ?? "null")|\(paid ?? "null")|\(cy)|\(fo)|\(ca)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ClrSearchField("Search name / account / phone", text: $q)
            filterBar.padding(.top, 8)
            casesList.padding(.top, 8)
        }
        .task(id: optsKey) {
            let br: String? = API.nb(branch)
            do {
                opts = try await API.shared.filterOptions(bank: p.bank, product: p.product, branch: br)
            } catch {
                opts = FilterOptions()
            }
        }
    }

    // MARK: filters

    private var filterBar: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(0..<paidOptions.count, id: \.self) { i in
                        let s: String? = paidOptions[i]
                        Chip(label: s ?? "All", selected: paid == s) { paid = s }
                    }
                }
            }
            if !opts.cycles.isEmpty {
                PfFilterLabel(text: "Cycle")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(opts.cycles, id: \.self) { c in
                            Chip(label: "Cyc \(c)", selected: cycles.contains(c)) { toggleCycle(c) }
                        }
                    }
                }
            }
            if !opts.fos.isEmpty {
                PfFilterLabel(text: "FOS")
                personRow(opts.fos, selected: fos) { id in toggleFos(id) }
            }
            if !opts.callers.isEmpty {
                PfFilterLabel(text: "Caller")
                personRow(opts.callers, selected: callers) { id in toggleCaller(id) }
            }
        }
    }

    private func personRow(_ people: [FilterPerson], selected: Set<Int>, toggle: @escaping (Int) -> Void) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(0..<people.count, id: \.self) { i in
                    let f: FilterPerson = people[i]
                    Chip(label: f.name ?? "#\(f.id)", selected: selected.contains(f.id)) { toggle(f.id) }
                }
            }
        }
    }

    private func toggleCycle(_ c: String) {
        if cycles.contains(c) { cycles.remove(c) } else { cycles.insert(c) }
    }

    private func toggleFos(_ id: Int) {
        if fos.contains(id) { fos.remove(id) } else { fos.insert(id) }
    }

    private func toggleCaller(_ id: Int) {
        if callers.contains(id) { callers.remove(id) } else { callers.insert(id) }
    }

    // MARK: list

    private var casesList: some View {
        let bank: String = p.bank
        let product: String = p.product
        let br: String? = branch
        let pd: String? = paid
        let cy: String = cycles.joined(separator: ",")
        let fo: String = fos.map { String($0) }.joined(separator: ",")
        let ca: String = callers.map { String($0) }.joined(separator: ",")
        return AsyncContent(key: AnyHashable(casesKey), load: {
            try await API.shared.portfolioCases(bank: bank, product: product, branch: br, paid: pd,
                                                cycles: cy, fosIds: fo, callerIds: ca)
        }) { cases, _ in
            PortfolioCaseResults(cases: cases, q: q, onOpenCase: onOpenCase, onOpenPerf: onOpenPerf)
        }
    }
}

private struct PfFilterLabel: View {
    let text: String

    var body: some View {
        Text(text).font(.labelSmall).foregroundColor(.Muted)
            .padding(.top, 10).padding(.bottom, 2)
    }
}

private struct PortfolioCaseResults: View {
    let cases: [Case]
    let q: String
    let onOpenCase: (Int) -> Void
    let onOpenPerf: (Int, String) -> Void

    private var gq: String { q.trimmingCharacters(in: .whitespaces).lowercased() }

    private var shown: [Case] {
        let needle = gq
        if needle.isEmpty { return cases }
        return cases.filter { c in
            let fields: [String] = [c.customerName, c.accountNo, c.phone].compactMap { $0 }
            return fields.contains(where: { $0.lowercased().contains(needle) })
        }
    }

    var body: some View {
        let list: [Case] = shown
        if list.isEmpty {
            EmptyState(text: gq.isEmpty ? "No cases match these filters." : "No cases match \"\(q)\".")
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(list) { c in
                        CaseCard(case: c, onClick: { onOpenCase(c.id) }, onOpenPerf: onOpenPerf)
                    }
                }
                .padding(.bottom, 16)
            }
        }
    }
}
