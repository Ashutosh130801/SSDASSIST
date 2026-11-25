import SwiftUI

/// Port of LeaveScreen.kt: balances, apply (incl. half-day), pending approvals for approver roles,
/// my leave history, and the all-employee leave history (HR / manager / head office) with filters.
struct LeaveView: View {
    @EnvironmentObject var app: AppState

    @State private var refresh: Int = 0
    @State private var showApply: Bool = false
    @State private var busy: Bool = false
    @State private var error: String? = nil
    @State private var histStatus: String = "all"
    @State private var histType: String = "all"
    @State private var histQ: String = ""

    init() {}

    private var user: User? { app.user }

    private var canApprove: Bool {
        guard let u = user else { return false }
        return u.isManager || u.isAdmin || u.role == "hr" || u.role == "headoffice"
    }

    /// Leave history (all employees) is an HR / manager function — admin is left out of it.
    private var canSeeHistory: Bool {
        guard let u = user else { return false }
        return u.isManager || u.role == "hr" || u.role == "headoffice"
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if let message = error {
                        Text(message).foregroundColor(.Bad).font(.bodyMedium)
                    }
                    balances
                    SectionTitle(canApprove ? "Pending approvals" : "My leave")
                    primaryList
                    if !canApprove {
                        SectionTitle("My leave history")
                        myHistory
                    }
                    if canSeeHistory {
                        SectionTitle("Leave history — all employees")
                        historyFilters
                        allHistory
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 90)
            }
            applyFab
        }
        .appBackground()
        .sheet(isPresented: $showApply) {
            LeaveApplySheet(busy: busy, error: error,
                            onDismiss: { if !busy { showApply = false } },
                            onConfirm: { body in apply(body) })
        }
    }

    // MARK: - FAB

    private var applyFab: some View {
        Button(action: {
            if !busy {
                error = nil
                showApply = true
            }
        }) {
            HStack(spacing: 6) {
                Image(systemName: "plus")
                Text("Apply").font(.labelLarge)
            }
            .foregroundColor(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .background(RoundedRectangle(cornerRadius: 16).fill(Color.BrandBlue))
            .shadow(color: Color.black.opacity(0.2), radius: 6, x: 0, y: 3)
        }
        .buttonStyle(.plain)
        .padding(16)
    }

    // MARK: - Sections

    private var balances: some View {
        AsyncContent(key: AnyHashable("bal:\(refresh)"), live: true, load: { () async throws -> [LeaveBalance] in
            try await API.shared.leaveBalance()
        }) { bal, _ in
            HStack(spacing: 8) {
                ForEach(Array(bal.enumerated()), id: \.offset) { _, b in
                    InfoCard(spacing: 2, padding: 12) {
                        Text(LeaveFmt.num(b.remaining ?? b.used))
                            .font(.titleMedium.weight(.bold)).foregroundColor(.BrandBlue)
                        Text(b.type).font(.labelSmall).foregroundColor(.Muted).lineLimit(1)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
    }

    private var primaryList: some View {
        let approve: Bool = canApprove
        let myId: Int = user?.id ?? -1
        return AsyncContent(key: AnyHashable("p:\(refresh)"), live: true, load: { () async throws -> [Leave] in
            try await API.shared.leaves(status: approve ? "pending" : nil, scope: approve ? "team" : "mine")
        }) { leaves, _ in
            if leaves.isEmpty {
                EmptyState(approve ? "Nothing to approve." : "No leave records.")
            } else {
                VStack(spacing: 10) {
                    ForEach(leaves) { lv in
                        LeaveCard(lv: lv, canApprove: approve && !busy && lv.userId != myId) { ok in
                            decide(lv, approve: ok)
                        }
                    }
                }
            }
        }
    }

    private var myHistory: some View {
        AsyncContent(key: AnyHashable("m:\(refresh)"), live: true, load: { () async throws -> [Leave] in
            try await API.shared.leaves(scope: "mine")
        }) { leaves, _ in
            if leaves.isEmpty {
                EmptyState("No leave records.")
            } else {
                LeaveMonthGrouped(leaves: leaves)
            }
        }
    }

    private var historyFilters: some View {
        let statuses: [(String, String)] = [("all", "All"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]
        let types: [(String, String)] = [("all", "All types"), ("Casual", "Casual"), ("Sick", "Sick"), ("Earned", "Earned"), ("Unpaid", "Unpaid")]
        return VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(0..<statuses.count, id: \.self) { i in
                        Chip(label: statuses[i].1, selected: histStatus == statuses[i].0) { histStatus = statuses[i].0 }
                    }
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(0..<types.count, id: \.self) { i in
                        Chip(label: types[i].1, selected: histType == types[i].0) { histType = types[i].0 }
                    }
                }
            }
            HRField("Search name, branch, type, reason", text: $histQ)
        }
    }

    private var allHistory: some View {
        let st: String? = histStatus == "all" ? nil : histStatus
        let ty: String? = histType == "all" ? nil : histType
        let qq: String = histQ.trimmingCharacters(in: .whitespaces)
        let query: String? = qq.isEmpty ? nil : qq
        let key: String = "hist:\(histStatus):\(histType):\(histQ):\(refresh)"
        return AsyncContent(key: AnyHashable(key), live: true, load: { () async throws -> [Leave] in
            try await API.shared.leaves(status: st, scope: "team", leaveType: ty, q: query)
        }) { leaves, _ in
            if leaves.isEmpty {
                EmptyState("No leave records match.")
            } else {
                LeaveMonthGrouped(leaves: leaves)
            }
        }
    }

    // MARK: - Actions

    private func decide(_ lv: Leave, approve: Bool) {
        if busy { return }
        busy = true
        error = nil
        Task { @MainActor in
            do {
                _ = try await API.shared.decideLeave(id: lv.id, approve: approve)
                refresh += 1
            } catch {
                self.error = LeaveFmt.leaveError(error)
            }
            busy = false
        }
    }

    private func apply(_ body: LeaveCreate) {
        if busy { return }
        busy = true
        error = nil
        Task { @MainActor in
            do {
                _ = try await API.shared.applyLeave(body: body)
                showApply = false
                refresh += 1
            } catch {
                self.error = LeaveFmt.leaveError(error)
            }
            busy = false
        }
    }
}

// MARK: - Helpers

enum LeaveFmt {
    static func num(_ v: Double) -> String {
        if v == v.rounded() && abs(v) < 1e9 { return String(Int(v)) }
        return "\(v)"
    }

    static func leaveError(_ e: Error) -> String {
        if let d = HRUtil.detail(e) { return d }
        return "Could not save the leave request. Check your connection and try again."
    }
}

/// History list grouped under month headers ("Mar 2025") by start date, newest first as returned.
struct LeaveMonthGrouped: View {
    let leaves: [Leave]

    private var groups: [(String, [Leave])] {
        var order: [String] = []
        var map: [String: [Leave]] = [:]
        for lv in leaves {
            let ym: String = String(lv.startDate.prefix(7))
            if map[ym] == nil {
                order.append(ym)
                map[ym] = []
            }
            map[ym]?.append(lv)
        }
        return order.map { ($0, map[$0] ?? []) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(groups.map { $0.0 }, id: \.self) { ym in
                let items: [Leave] = groups.first(where: { $0.0 == ym })?.1 ?? []
                Text("\(DateUtil.monthLabel(ym)) · \(items.count)")
                    .font(.labelMedium.weight(.semibold)).foregroundColor(.BrandBlue)
                    .padding(.top, 4)
                ForEach(items) { lv in
                    LeaveCard(lv: lv, canApprove: false) { _ in }
                }
            }
        }
    }
}

struct LeaveCard: View {
    let lv: Leave
    let canApprove: Bool
    let onDecide: (Bool) -> Void

    private var daysText: String {
        let d: Double = lv.daysEffective ?? ((lv.halfDay == true) ? 0.5 : Double(lv.days))
        let half: String = (lv.halfDay == true) ? " · Half day" : ""
        return "\(lv.leaveType ?? "Leave") · \(LeaveFmt.num(d)) day(s)\(half)"
    }

    var body: some View {
        InfoCard(spacing: 3) {
            HStack(alignment: .top) {
                details
                Spacer(minLength: 8)
                StatusChip(lv.status)
            }
            if canApprove && lv.status.lowercased() == "pending" {
                HStack(spacing: 8) {
                    HRFilledButton("Approve", color: .Good) { onDecide(true) }
                    HROutlinedButton("Reject") { onDecide(false) }
                }
                .padding(.top, 8)
            }
        }
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(lv.userName ?? (lv.leaveType ?? "Leave")).font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
            Text(daysText).font(.bodySmall).foregroundColor(.Muted)
            Text("\(DateUtil.humanDate(lv.startDate)) → \(DateUtil.humanDate(lv.endDate))")
                .font(.bodySmall).foregroundColor(.Muted)
            if let r = lv.reason {
                Text(r).font(.bodySmall).foregroundColor(.Muted)
            }
            partialLine
            noteLine
        }
    }

    @ViewBuilder private var partialLine: some View {
        if lv.partial == true, let rs = lv.requestedStart {
            let asked: String = lv.requestedDays.map { LeaveFmt.num($0) } ?? ""
            Text("Partly approved — asked \(asked) day(s): \(DateUtil.humanDate(rs)) → \(DateUtil.humanDate(lv.requestedEnd ?? rs))")
                .font(.bodySmall).foregroundColor(.Muted)
        }
    }

    @ViewBuilder private var noteLine: some View {
        if let n = lv.decisionNote, !n.trimmingCharacters(in: .whitespaces).isEmpty {
            let prefix: String = lv.status.lowercased() == "rejected" ? "Reason: " : "Note: "
            Text(prefix + n).font(.bodySmall.weight(.semibold)).foregroundColor(.TextDark)
        }
    }
}

/// Kotlin ApplyLeaveDialog as a sheet.
struct LeaveApplySheet: View {
    let busy: Bool
    let error: String?
    let onDismiss: () -> Void
    let onConfirm: (LeaveCreate) -> Void

    private var types: [String] { ["Casual", "Sick", "Earned", "Unpaid"] }

    @State private var type: String = "Casual"
    @State private var startIso: String = DateUtil.plusDaysIso(0)
    @State private var endIso: String = DateUtil.plusDaysIso(0)
    @State private var reason: String = ""
    @State private var halfDay: Bool = false

    private var days: Int { DateUtil.daysInclusive(startIso, endIso) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Type").font(.labelSmall).foregroundColor(.Muted)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(types, id: \.self) { t in
                                Chip(label: t, selected: type == t) { type = t }
                            }
                        }
                    }
                    HStack(spacing: 6) {
                        Chip(label: "Full day(s)", selected: !halfDay) { if !busy { halfDay = false } }
                        Chip(label: "Half day (0.5)", selected: halfDay) {
                            if !busy {
                                halfDay = true
                                endIso = startIso
                            }
                        }
                    }
                    DatePickerField(label: "Start date", iso: startIso) { picked in pickStart(picked) }
                    if !halfDay {
                        DatePickerField(label: "End date", iso: endIso) { picked in pickEnd(picked) }
                    }
                    Text(durationText).font(.labelSmall).foregroundColor(.Muted)
                    HRField("Reason (optional)", text: $reason, multiline: true)
                    if let e = error {
                        Text(e).foregroundColor(.Bad).font(.bodySmall)
                    }
                    HRFilledButton(busy ? "Submitting…" : "Submit", enabled: !busy && days > 0) { submit() }
                        .padding(.top, 6)
                }
                .padding(20)
            }
            .navigationTitle("Apply for leave")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onDismiss() }.disabled(busy)
                }
            }
        }
        .interactiveDismissDisabled(busy)
    }

    private var durationText: String {
        if halfDay { return "Duration: 0.5 day. Counts in attendance only after approval." }
        return "Duration: \(days) day\(days > 1 ? "s" : "")"
    }

    private func pickStart(_ picked: String) {
        startIso = picked
        let e: Int64 = DateUtil.millisFromIso(endIso) ?? 0
        let p: Int64 = DateUtil.millisFromIso(picked) ?? 0
        if halfDay || e < p { endIso = picked }
    }

    private func pickEnd(_ picked: String) {
        let p: Int64 = DateUtil.millisFromIso(picked) ?? 0
        let s: Int64 = DateUtil.millisFromIso(startIso) ?? 0
        endIso = p < s ? startIso : picked
    }

    private func submit() {
        let r: String = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        onConfirm(LeaveCreate(leaveType: type, startDate: startIso,
                              endDate: halfDay ? startIso : endIso,
                              reason: r.isEmpty ? nil : reason, halfDay: halfDay))
    }
}
