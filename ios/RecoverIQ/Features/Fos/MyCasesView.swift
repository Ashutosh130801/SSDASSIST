import SwiftUI

// Port of MyCasesScreen (ui/fos/FieldAgentScreens.kt): month → portfolio (bank·product) → cases drill-down,
// PIN / area search across portfolios, PIN chips, status filters, sort chips, PTP reminders banner,
// Excel / PDF export of the filtered set. Escalated (locked) cases render via CaseCard's badge.

struct MyCasesView: View {
    var onOpenCase: (Int) -> Void

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    @EnvironmentObject var app: AppState

    @State private var sel: String = "All"
    @State private var query: String = ""
    @State private var sort: String = "Pending ↑"
    @State private var pin: String? = nil
    @State private var areaQuery: String = ""
    @State private var month: String? = nil
    @State private var portfolio: String? = nil      // "bank||product"
    @State private var busy: Bool = false
    @State private var caseData: [Case]? = nil
    @State private var reminders: RemindersResponse? = nil
    @State private var loadError: String? = nil
    @State private var liveKey: Int = 0
    @State private var retry: Int = 0
    @State private var scrollTopTick: Int = 0

    private struct LoadKey: Equatable { let live: Int; let retry: Int }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    Color.clear.frame(height: 0).id("top")
                    SectionTitle("My accounts").padding(.horizontal, 16)
                    MyCasesRemindersBanner(data: reminders, onOpenCase: onOpenCase)
                    loadStatus
                    if let cases = caseData {
                        content(cases)
                    }
                }
                .padding(.top, 12)
                .padding(.bottom, 160)
            }
            .onChange(of: scrollTopTick) { _ in
                withAnimation { proxy.scrollTo("top", anchor: .top) }
            }
        }
        .task(id: LoadKey(live: liveKey, retry: retry)) { await loadCases() }
        .task(id: LoadKey(live: liveKey, retry: retry)) { await loadReminders() }
        .onReceive(Realtime.shared.changed) { _ in liveKey += 1 }
    }

    // MARK: - Loading

    private func loadCases() async {
        loadError = nil
        do {
            let v: [Case] = try await API.shared.myCases()
            caseData = v
        } catch {
            if error is CancellationError { return }
            loadError = caseData == nil ? "Couldn't load your accounts. Please retry."
                : "Couldn't refresh. Showing previously loaded accounts."
        }
    }

    private func loadReminders() async {
        do {
            let r: RemindersResponse = try await API.shared.reminders()
            reminders = r
        } catch {
            // Retain existing reminders during a temporary connection failure.
        }
    }

    private func changePortfolio(_ value: String?) {
        portfolio = value
        pin = nil
        scrollTopTick += 1
    }

    @ViewBuilder private var loadStatus: some View {
        if let message = loadError {
            VStack(alignment: .leading, spacing: 4) {
                Text(message).foregroundColor(.Bad)
                Button("Retry") { retry += 1 }.foregroundColor(.BrandBlue)
            }
            .padding(.horizontal, 16)
        }
        if caseData == nil && loadError == nil {
            HStack { Spacer(); LogoLoader(); Spacer() }.padding(24)
        }
    }

    // MARK: - Content

    @ViewBuilder private func content(_ cases: [Case]) -> some View {
        if cases.isEmpty {
            Text("No cases assigned to you yet.").foregroundColor(.Muted).padding(16)
        } else {
            let months: [String] = FosCaseLogic.months(cases)
            let curMonth: String = month ?? months.first ?? "—"
            let monthCases: [Case] = cases.filter { FosCaseLogic.monthOf($0) == curMonth }
            MyCasesMonthChips(months: months, cases: cases, current: curMonth) { m in
                month = m
                changePortfolio(nil)
            }
            if let port = portfolio {
                portfolioCases(monthCases: monthCases, curMonth: curMonth, port: port)
            } else if !areaQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                areaSearchField
                areaResults(monthCases: monthCases, curMonth: curMonth)
            } else {
                areaSearchField
                portfolioPicker(monthCases: monthCases, curMonth: curMonth)
            }
        }
    }

    private var areaSearchField: some View {
        FosSearchField(text: $areaQuery, placeholder: "Search by PIN code or area (all portfolios)", showClear: true)
            .padding(.horizontal, 16).padding(.vertical, 4)
    }

    @ViewBuilder private func areaResults(monthCases: [Case], curMonth: String) -> some View {
        let hits: [Case] = FosCaseLogic.stableSorted(monthCases.filter { FosCaseLogic.areaMatch($0, areaQuery) }) {
            a, b in a.pendingAmount > b.pendingAmount
        }
        let trimmedQ: String = areaQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        Text("\(hits.count) account\(FosCaseLogic.plural(hits.count)) in \(FosCaseLogic.monthLabel(curMonth)) matching \"\(trimmedQ)\"  ·  pending \(inr(FosCaseLogic.sumPending(hits)))")
            .foregroundColor(.Muted).font(.bodyMedium)
            .padding(.leading, 16).padding(.top, 4).padding(.bottom, 2)
        ForEach(hits) { c in
            MyCasesAreaHitRow(c: c, onOpen: { onOpenCase(c.id) })
                .padding(.horizontal, 16)
        }
    }

    @ViewBuilder private func portfolioPicker(monthCases: [Case], curMonth: String) -> some View {
        let ports: [FosPortfolio] = FosCaseLogic.portfolios(monthCases)
        Text("Portfolios in \(FosCaseLogic.monthLabel(curMonth))")
            .foregroundColor(.Muted).font(.bodyMedium)
            .padding(.leading, 16).padding(.top, 6).padding(.bottom, 2)
        ForEach(ports) { p in
            MyCasesPortfolioCard(portfolio: p) { changePortfolio(p.key) }
                .padding(.horizontal, 16)
        }
    }

    // MARK: - Case list for the selected month + portfolio

    @ViewBuilder private func portfolioCases(monthCases: [Case], curMonth: String, port: String) -> some View {
        let parts: (String, String) = FosCaseLogic.splitKey(port)
        let bank: String = parts.0
        let prod: String = parts.1
        let portCases: [Case] = monthCases.filter { FosCaseLogic.portKey($0) == port }
        let ordered: [Case] = orderedCases(portCases)
        let pinCounts: [FosPinCount] = FosCaseLogic.pinCounts(portCases)
        let exportTitle: String = "\(bank) · \(prod) · \(FosCaseLogic.monthLabel(curMonth))"
        let exportBase: String = FosCaseLogic.exportBase(bank: bank, product: prod, month: curMonth)

        MyCasesContextBar(bank: bank, product: prod, count: ordered.count, busy: busy,
                          onBack: { changePortfolio(nil) },
                          onExport: { fmt in export(ordered, fmt: fmt, base: exportBase, title: exportTitle) })
            .padding(.horizontal, 16).padding(.vertical, 4)
        FosSearchField(text: $query, placeholder: "Search name / account / phone / PIN / area", showClear: false)
            .padding(.horizontal, 16).padding(.vertical, 2)
        if pinCounts.count > 1 {
            MyCasesPinChips(pins: pinCounts, selected: pin) { p in pin = p }
        }
        MyCasesFilterChips(portCases: portCases, selected: sel) { s in sel = s }
        MyCasesSortChips(selected: sort) { s in sort = s }
        if ordered.isEmpty {
            let q: String = query.trimmingCharacters(in: .whitespacesAndNewlines)
            Text(q.isEmpty ? "No cases in this filter." : "No cases match \"\(query)\".")
                .foregroundColor(.Muted).padding(16)
        } else {
            ForEach(ordered) { c in
                CaseCard(case: c, onClick: { onOpenCase(c.id) })
                    .padding(.horizontal, 16)
            }
        }
    }

    private func orderedCases(_ portCases: [Case]) -> [Case] {
        let pred: FosCaseFilter = FosCaseLogic.filters.first { $0.label == sel } ?? FosCaseLogic.filters[0]
        let q: String = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let sorter: FosCaseSort = FosCaseLogic.sorts.first { $0.label == sort } ?? FosCaseLogic.sorts[0]
        let pinSel: String? = pin
        let filtered: [Case] = portCases.filter { c in
            pred.test(c) && FosCaseLogic.matches(c, q) && (pinSel == nil || FosCaseLogic.pinsOf(c).contains(pinSel ?? ""))
        }
        return FosCaseLogic.stableSorted(filtered, by: sorter.before)
    }

    // MARK: - Export

    private func export(_ ordered: [Case], fmt: String, base: String, title: String) {
        if busy || ordered.isEmpty { return }
        busy = true
        let ids: [Int] = ordered.map { $0.id }
        Task { @MainActor in
            await exportAndShare(ids: ids, fmt: fmt, baseName: base, title: title)
            busy = false
        }
    }

    /// Download the given cases as Excel/PDF from the backend and open the share sheet.
    @MainActor private func exportAndShare(ids: [Int], fmt: String, baseName: String, title: String) async {
        do {
            let ext: String = fmt == "pdf" ? "pdf" : "xlsx"
            let downloaded: URL = try await API.shared.exportCases(ids: ids, fmt: fmt, title: title)
            let url: URL = renamed(downloaded, to: "\(baseName.isEmpty ? "Cases" : baseName).\(ext)")
            Files.share(url)
        } catch {
            app.toast("Download failed: \(error.localizedDescription)")
        }
    }

    /// Give the temp file the Android-style name (Cases_<bank>_<product>_<month>.xlsx); falls back to the original.
    private func renamed(_ src: URL, to name: String) -> URL {
        let fm = FileManager.default
        let dir: URL = fm.temporaryDirectory.appendingPathComponent("riq-export-" + UUID().uuidString, isDirectory: true)
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
            let dst: URL = dir.appendingPathComponent(name)
            try fm.copyItem(at: src, to: dst)
            return dst
        } catch {
            return src
        }
    }
}
