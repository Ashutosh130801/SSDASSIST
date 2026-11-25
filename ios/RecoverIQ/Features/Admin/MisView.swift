import SwiftUI

// Port of ui/common/MisScreen.kt — full MIS for a portfolio: month chips + Flipkart-style Filters sheet,
// portfolio picker (bank → product), removable active-filter chips and every pivot / leaderboard /
// insight block of the /api/mis payload (MisSections.swift). View-only; Excel downloads via the menu.
struct MisView: View {
    @EnvironmentObject var app: AppState

    @State private var mb: String = "current"
    @State private var bank: String = ""
    @State private var product: String = ""
    @State private var ports: [ProductSummary] = []
    @State private var fopts: FilterOptions = FilterOptions()
    @State private var areas: [String] = []
    @State private var filters: MisFilters = MisFilters()
    @State private var sheetOpen: Bool = false
    @State private var downloading: Bool = false

    init() {}

    private static let months: [(String, String)] = [
        ("current", "This month"), ("next", "Next month"), ("last", "Last month"), ("", "All months"),
    ]

    private var banks: [String] { Array(Set(ports.map { $0.bank })).sorted() }

    private var prods: [String] {
        Array(Set(ports.filter { $0.bank == bank }.map { $0.product })).sorted()
    }

    /// Branch options come from the selected portfolio row.
    private var branchOpts: [String] {
        let rows: [ProductSummary] = ports.filter { $0.bank == bank && $0.product == product }
        var set: Set<String> = []
        for r in rows {
            for b in r.branches where !b.branch.trimmingCharacters(in: .whitespaces).isEmpty { set.insert(b.branch) }
        }
        return set.sorted()
    }

    private var ready: Bool { !bank.isEmpty && !product.isEmpty }

    private var misKey: String { "mis|\(bank)|\(product)|\(mb)|\(filters.key)" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                SectionTitle("MIS").padding(.leading, 4)
                monthBar
                portfolioPicker
                if filters.count > 0 {
                    MisActiveFilterChips(filters: filters, fopts: fopts, onChange: { filters = $0 })
                }
                if ready {
                    misContent
                } else if ports.isEmpty {
                    Text("No portfolios to show.").font(.bodySmall).foregroundColor(.Muted).padding(8)
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 24)
        }
        .task { await loadPorts() }
        .onChange(of: bank) { _ in syncProduct() }
        .task(id: "\(bank)|\(product)") { await loadOptions() }
        .sheet(isPresented: $sheetOpen) {
            MisFilterSheet(branchOpts: branchOpts, areas: areas, fopts: fopts, initial: filters,
                           onApply: { f in
                               filters = f
                               sheetOpen = false
                           },
                           onDismiss: { sheetOpen = false })
                .presentationDetents([.large])
        }
    }

    // MARK: bars

    private var monthBar: some View {
        HStack(spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(0..<MisView.months.count, id: \.self) { i in
                        let m = MisView.months[i]
                        Chip(label: m.1, selected: mb == m.0) { mb = m.0 }
                    }
                }
            }
            MisFilterButton(count: filters.count) { sheetOpen = true }
            downloadMenu
        }
    }

    private var downloadMenu: some View {
        Menu {
            Button(action: { download(pivot: false) }) {
                Label("MIS tables (Excel)", systemImage: "tablecells")
            }
            Button(action: { download(pivot: true) }) {
                Label("MIS pivot workbook (Excel)", systemImage: "square.grid.3x3")
            }
        } label: {
            ZStack {
                if downloading {
                    ProgressView().scaleEffect(0.8)
                } else {
                    Image(systemName: "square.and.arrow.down").font(.system(size: 15, weight: .semibold))
                }
            }
            .foregroundColor(.BrandBlue)
            .frame(width: 38, height: 36)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.GlassStroke, lineWidth: 1))
        }
        .disabled(!ready || downloading)
    }

    private var portfolioPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Portfolio").font(.labelSmall).foregroundColor(.Muted).padding(.leading, 4)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(banks, id: \.self) { b in
                        Chip(label: b, selected: bank == b) {
                            bank = b
                            product = ""
                            syncProduct()
                        }
                    }
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(prods, id: \.self) { p in
                        Chip(label: p, selected: product == p) { product = p }
                    }
                }
            }
        }
    }

    @ViewBuilder private var misContent: some View {
        let b: String = bank
        let p: String = product
        let m: String = mb
        let f: MisFilters = filters
        AsyncContent(key: AnyHashable(misKey), live: true, load: {
            try await API.shared.misOrdered(bank: b, product: p, monthBucket: m, area: f.area,
                                            branch: f.csvStr(f.branches), cycles: f.csvStr(f.cycles),
                                            fosIds: f.csv(f.fos), callerIds: f.csv(f.callers),
                                            orderedBlocks: MisDefs.kvBlocks.map { $0.0 })
        }) { payload, _ in
            MisBodyView(payload: payload)
        }
        .frame(minHeight: 200)
    }

    // MARK: loading

    private func loadPorts() async {
        if !ports.isEmpty { return }
        let list: [ProductSummary] = (try? await API.shared.productSummary()) ?? []
        ports = list
        if bank.isEmpty, let first = banks.first { bank = first }
        syncProduct()
    }

    private func syncProduct() {
        let ps: [String] = prods
        if !ps.isEmpty && !ps.contains(product) { product = ps[0] }
    }

    /// Reset filters when the portfolio changes; reload cycle/FOS/caller options + areas.
    private func loadOptions() async {
        filters = MisFilters()
        guard ready else { return }
        let b: String = bank
        let p: String = product
        let fo: FilterOptions = (try? await API.shared.filterOptions(bank: b, product: p)) ?? FilterOptions()
        let ar: [String] = (try? await API.shared.areas(bank: b, product: p)) ?? []
        if b == bank && p == product {
            fopts = fo
            areas = ar
        }
    }

    // MARK: downloads

    private func download(pivot: Bool) {
        guard ready, !downloading else { return }
        downloading = true
        let b: String = bank
        let p: String = product
        let m: String = mb
        let f: MisFilters = filters
        Task {
            do {
                let url: URL
                if pivot {
                    url = try await API.shared.misPivotXlsx(bank: b, product: p, monthBucket: m,
                                                            branch: f.csvStr(f.branches))
                } else {
                    url = try await API.shared.misDownload(bank: b, product: p, monthBucket: m, area: f.area,
                                                           branch: f.csvStr(f.branches), cycles: f.csvStr(f.cycles),
                                                           fosIds: f.csv(f.fos), callerIds: f.csv(f.callers))
                }
                downloading = false
                Files.share(url)
            } catch {
                downloading = false
                app.toast(error.localizedDescription)
            }
        }
    }
}
