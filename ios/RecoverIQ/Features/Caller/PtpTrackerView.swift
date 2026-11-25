import SwiftUI

/// Port of ui/caller/CallerScreens.kt `PtpTrackerScreen` — overdue / today / upcoming promises with a
/// promise-date range, searchable caller & FOS filters and the last 5 notes per case.
struct PtpTrackerView: View {
    var onOpenCase: (Int) -> Void

    @State private var bucket: String = "overdue"
    @State private var dFrom: String = ""
    @State private var dTo: String = ""
    @State private var callerId: Int? = nil
    @State private var fosId: Int? = nil

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    private var loadKey: String {
        return "\(dFrom)|\(dTo)|\(callerId.map { String($0) } ?? "null")|\(fosId.map { String($0) } ?? "null")"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Promise-to-pay tracker")
                .padding(.top, 12).padding(.leading, 4)
            dateRow.padding(.bottom, 6)
            AsyncContent(key: AnyHashable(loadKey),
                         load: {
                             try await API.shared.ptpTracker(dateFrom: dFrom, dateTo: dTo, callerId: callerId, fosId: fosId)
                         }) { resp, _ in
                PtpTrackerBody(resp: resp, bucket: $bucket, callerId: $callerId, fosId: $fosId, onOpenCase: onOpenCase)
            }
        }
        .padding(.horizontal, 12)
    }

    private var dateRow: some View {
        HStack(spacing: 6) {
            DatePickerField(label: "From", iso: $dFrom).frame(maxWidth: .infinity)
            DatePickerField(label: "To", iso: $dTo).frame(maxWidth: .infinity)
            if !dFrom.trimmingCharacters(in: .whitespaces).isEmpty || !dTo.trimmingCharacters(in: .whitespaces).isEmpty {
                Button("Clear") {
                    dFrom = ""
                    dTo = ""
                }
            }
        }
    }
}

private struct PtpTrackerBody: View {
    let resp: PtpResponse
    @Binding var bucket: String
    @Binding var callerId: Int?
    @Binding var fosId: Int?
    let onOpenCase: (Int) -> Void

    private let buckets: [String] = ["overdue", "today", "upcoming"]

    private var rows: [PtpRow] { resp.rows.filter { $0.bucket == bucket } }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                ClrStaffSearchDropdown(allLabel: "All callers", options: resp.callers, value: $callerId)
                ClrStaffSearchDropdown(allLabel: "All FOS", options: resp.fos, value: $fosId)
            }
            .padding(.bottom, 6)
            HStack(spacing: 6) {
                ForEach(buckets, id: \.self) { b in
                    let n: Int = resp.counts[b] ?? 0
                    Chip(label: "\(b.prefix(1).uppercased() + String(b.dropFirst())) (\(n))", selected: bucket == b) {
                        bucket = b
                    }
                }
            }
            if rows.isEmpty {
                EmptyState(text: "No promises in this group.")
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(0..<rows.count, id: \.self) { i in
                            ClrPtpCard(row: rows[i], onOpenCase: onOpenCase)
                        }
                    }
                    .padding(.top, 8).padding(.bottom, 16)
                }
            }
        }
    }
}

private struct ClrPtpCard: View {
    let row: PtpRow
    let onOpenCase: (Int) -> Void

    private var promise: String {
        var s: String = ""
        if let a = row.ptpAmount { s += "\(inr(a)) promised" }
        if let d = row.promisedDate {
            if !s.isEmpty { s += " · " }
            s += "by \(DateUtil.humanDate(d))"
        }
        return s.trimmingCharacters(in: .whitespaces).isEmpty ? "Promise to pay" : s
    }

    private var caller: String? {
        let c = row.case
        if let n = c.assignedCallerName {
            return n + (c.assignedCallerCode.map { " (\($0))" } ?? "")
        }
        return c.callerName
    }

    private var fos: String? {
        let c = row.case
        if let n = c.assignedFosName {
            return n + (c.assignedFosCode.map { " (\($0))" } ?? "")
        }
        return c.fosName
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            CaseCard(case: row.case, onClick: { onOpenCase(row.case.id) }, subtitle: promise)
            if caller != nil || fos != nil {
                Text("📞 Caller: \(caller ?? "—")    🧍 FOS: \(fos ?? "—")")
                    .font(.labelSmall).foregroundColor(.Muted)
                    .padding(.leading, 12).padding(.top, 1)
            }
            if !row.notes.isEmpty {
                notesBlock
            }
        }
    }

    private var notesBlock: some View {
        let shown: [CaseNote] = Array(row.notes.prefix(5))
        return VStack(alignment: .leading, spacing: 1) {
            Text("Recent notes").font(.labelSmall).foregroundColor(.Muted)
            ForEach(0..<shown.count, id: \.self) { i in
                Text(noteLine(shown[i])).font(.labelSmall).foregroundColor(.Muted).padding(.top, 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, 12).padding(.top, 2).padding(.bottom, 2)
    }

    private func nonBlank(_ s: String?) -> String? {
        guard let s = s, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return s
    }

    private func noteLine(_ n: CaseNote) -> String {
        let head: String = [nonBlank(n.disposition), nonBlank(n.text)].compactMap { $0 }.joined(separator: ": ")
        let tail: String = [nonBlank(n.by), nonBlank(n.at)].compactMap { $0 }.joined(separator: ", ")
        let icon: String = n.source == "visit" ? "🧍 " : "📞 "
        return icon + head + (tail.isEmpty ? "" : "  — \(tail)")
    }
}

/// Single-select people picker with type-to-search (Kotlin `ClrStaffSearchDropdown`). nil = the "all" choice.
private struct ClrStaffSearchDropdown: View {
    let allLabel: String
    let options: [StaffOpt]
    @Binding var value: Int?

    @State private var open: Bool = false

    private var selectedLabel: String {
        return options.first(where: { $0.id == value })?.label ?? allLabel
    }

    var body: some View {
        Button(action: { open = true }) {
            HStack(spacing: 4) {
                Text(selectedLabel).lineLimit(1).font(.system(size: 14, weight: .medium))
                Spacer(minLength: 0)
                Image(systemName: "chevron.down").font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(.BrandBlue)
            .padding(.horizontal, 12).padding(.vertical, 9)
            .frame(maxWidth: .infinity)
            .background(Capsule().fill(Color.CardWhite))
            .overlay(Capsule().stroke(Color.StrokeSoft, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $open) {
            ClrStaffPickerSheet(allLabel: allLabel, options: options,
                             onPick: { (picked: Int?) in
                                 value = picked
                                 open = false
                             },
                             onClose: { open = false })
        }
    }
}

private struct ClrStaffPickerSheet: View {
    let allLabel: String
    let options: [StaffOpt]
    let onPick: (Int?) -> Void
    let onClose: () -> Void

    @State private var query: String = ""

    private var shown: [StaffOpt] {
        let q = query.trimmingCharacters(in: .whitespaces)
        if q.isEmpty { return options }
        return options.filter { $0.label.range(of: q, options: .caseInsensitive) != nil }
    }

    var body: some View {
        NavigationStack {
            List {
                Button(allLabel) { onPick(nil) }
                ForEach(shown) { o in
                    Button(o.label) { onPick(o.id) }
                }
                if shown.isEmpty {
                    Text("No match").foregroundColor(.Muted)
                }
            }
            .listStyle(.plain)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search…")
            .navigationTitle(allLabel)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { onClose() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
