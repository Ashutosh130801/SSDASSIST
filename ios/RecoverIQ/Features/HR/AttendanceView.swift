import SwiftUI

/// Port of AttendanceScreens.kt `AttendanceScreen`: today's board (KPIs, role filter, search, per-person
/// cards with presence / check-in GPS / live FOS position) + monthly / salary-cycle matrix with .xlsx download.
struct AttendanceView: View {
    @EnvironmentObject var app: AppState

    @State private var tab: String = "day"
    @State private var role: String = ""
    @State private var q: String = ""
    /// Salary cycle = 21st → 20th. 0 = the running cycle that contains today; 1 = the one before.
    @State private var cycleBack: Int = 0
    @State private var downloading: Bool = false

    init() {}

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                SectionTitle("Attendance")
                    .padding(.top, 12)
                    .padding(.leading, 4)
                tabChips
                if tab == "cycle" { cycleChips }
                if tab == "month" || tab == "cycle" {
                    monthSection
                } else {
                    daySection
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 24)
        }
        .appBackground()
    }

    // MARK: - Chips

    private var tabChips: some View {
        HStack(spacing: 6) {
            Chip(label: "Today", selected: tab == "day") { tab = "day" }
            Chip(label: "This month", selected: tab == "month") { tab = "month" }
            Chip(label: "💰 Salary cycle", selected: tab == "cycle") { tab = "cycle" }
        }
    }

    private var cycleChips: some View {
        let c: (String, String) = AttendanceView.cycleRange(back: cycleBack)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Chip(label: "This cycle", selected: cycleBack == 0) { cycleBack = 0 }
                Chip(label: "Previous cycle", selected: cycleBack == 1) { cycleBack = 1 }
            }
            Text("\(c.0)  →  \(c.1)").font(.labelMedium).foregroundColor(.Muted)
        }
    }

    private var searchField: some View {
        HRField("Search name / ID", text: $q)
    }

    // MARK: - Month / cycle

    private var monthSection: some View {
        let isCycle: Bool = tab == "cycle"
        let cyc: (String, String) = AttendanceView.cycleRange(back: cycleBack)
        let r: String = role
        let key: String = "attm|\(tab)|\(cyc.0)|\(r)"
        return AsyncContent(key: AnyHashable(key), live: true, load: { () async throws -> [String: JSONValue] in
            if isCycle {
                return try await API.shared.attMonth(month: nil, role: r, start: cyc.0, end: cyc.1)
            }
            return try await API.shared.attMonth(month: nil, role: r)
        }) { m, _ in
            monthContent(m, isCycle: isCycle, cycle: cyc)
        }
    }

    @ViewBuilder
    private func monthContent(_ m: [String: JSONValue], isCycle: Bool, cycle: (String, String)) -> some View {
        let days: [String] = m.arr("days").map { $0.text }
        let people: [[String: JSONValue]] = filteredPeople(m)
        searchField
        if m.bool("can_download") == true {
            let mm: String = m.str("month") ?? ""
            HRFilledButton(downloading ? "Downloading…" : "⬇ Download sheet (.xlsx)", enabled: !downloading) {
                download(month: mm, start: isCycle ? cycle.0 : nil, end: isCycle ? cycle.1 : nil)
            }
        }
        AttMonthMatrix(days: days, people: people)
        Text("P Present · L Late · LV Leave · HD Half-day leave · A Absent · W Week-off. HD = 0.5 leave plus 0.5 present if checked in; otherwise 0.5 absent on past dates only.")
            .font(.labelSmall).foregroundColor(.Muted)
    }

    private func filteredPeople(_ m: [String: JSONValue]) -> [[String: JSONValue]] {
        let all: [[String: JSONValue]] = m.arr("people").compactMap { $0.object }
        let needle: String = q.trimmingCharacters(in: .whitespaces)
        if needle.isEmpty { return all }
        return all.filter { p in
            let n: String = p.str("name") ?? ""
            let c: String = p.str("emp_code") ?? ""
            return n.localizedCaseInsensitiveContains(needle) || c.localizedCaseInsensitiveContains(needle)
        }
    }

    /// Save the attendance .xlsx and open the share sheet (Kotlin downloadAttendanceSheet).
    private func download(month: String, start: String?, end: String?) {
        downloading = true
        let r: String = role
        Task { @MainActor in
            do {
                let url: URL
                let name: String
                if let s = start, let e = end {
                    url = try await API.shared.attDownload(month: nil, role: r, start: s, end: e)
                    name = "Attendance_\(s)_to_\(e).xlsx"
                } else {
                    url = try await API.shared.attDownload(month: month, role: r)
                    name = "Attendance_\(month).xlsx"
                }
                HRUtil.shareRenamed(url, as: name)
            } catch {
                app.toast(error.localizedDescription)
            }
            downloading = false
        }
    }

    // MARK: - Day board

    private var daySection: some View {
        let r: String = role
        return AsyncContent(key: AnyHashable("att|\(r)"), live: true, load: { () async throws -> AttDay in
            try await API.shared.attDay(date: nil, role: r)
        }) { d, _ in
            dayContent(d)
        }
    }

    @ViewBuilder
    private func dayContent(_ d: AttDay) -> some View {
        let roles: [String] = Array(Set(d.rows.compactMap { $0.role }.filter { !$0.isEmpty })).sorted()
        let rows: [AttRow] = filteredRows(d.rows)
        HStack(spacing: 8) {
            AttKpi(label: "Present", value: "\(d.summary.present)", color: .Good)
            AttKpi(label: "Late", value: "\(d.summary.late)", color: .Warn)
            AttKpi(label: "Absent", value: "\(d.summary.absent)", color: Color(argb: 0xFFDC2626))
            AttKpi(label: "Online", value: "\(d.summary.online)", color: .BrandBlue)
        }
        Text("On leave: \(d.summary.leave) full day · \(d.summary.halfLeave) half day")
            .font(.bodySmall).foregroundColor(.BrandBlue)
        searchField
        if !roles.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    Chip(label: "All", selected: role.isEmpty) { role = "" }
                    ForEach(roles, id: \.self) { rr in
                        Chip(label: rr, selected: role == rr) { role = rr }
                    }
                }
            }
        }
        ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
            AttCard(r: row)
        }
        if rows.isEmpty {
            Text("No one to show.").font(.bodySmall).foregroundColor(.Muted)
        }
    }

    private func filteredRows(_ rows: [AttRow]) -> [AttRow] {
        let needle: String = q.trimmingCharacters(in: .whitespaces)
        if needle.isEmpty { return rows }
        return rows.filter { r in
            (r.name ?? "").localizedCaseInsensitiveContains(needle) ||
                (r.empCode ?? "").localizedCaseInsensitiveContains(needle)
        }
    }

    // MARK: - Salary cycle range (IST calendar)

    static func cycleRange(back: Int) -> (String, String) {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = DateUtil.ist
        let now = Date()
        let day: Int = cal.component(.day, from: now)
        let addEnd: Int = (day >= 21 ? 1 : 0) - back
        var comps: DateComponents = cal.dateComponents([.year, .month], from: now)
        comps.day = 1
        let first: Date = cal.date(from: comps) ?? now
        let endMonth: Date = cal.date(byAdding: .month, value: addEnd, to: first) ?? first
        var endComps: DateComponents = cal.dateComponents([.year, .month], from: endMonth)
        endComps.day = 20
        let end: Date = cal.date(from: endComps) ?? endMonth
        let startMonth: Date = cal.date(byAdding: .month, value: -1, to: endMonth) ?? endMonth
        var startComps: DateComponents = cal.dateComponents([.year, .month], from: startMonth)
        startComps.day = 21
        let start: Date = cal.date(from: startComps) ?? startMonth
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = cal
        f.timeZone = DateUtil.ist
        f.dateFormat = "yyyy-MM-dd"
        return (f.string(from: start), f.string(from: end))
    }
}
