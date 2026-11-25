import SwiftUI

/// Port of ChangeRequestsScreen.kt — HR / Admin review employees' profile change requests:
/// approve (applies the change) or reject, with an optional remark.
struct ChangeRequestsView: View {
    @EnvironmentObject var app: AppState

    @State private var refresh: Int = 0
    @State private var status: String = "pending"
    @State private var query: String = ""
    @State private var notes: [Int: String] = [:]
    @State private var busyId: Int? = nil

    init() {}

    private var statuses: [(String, String)] { [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("all", "All")] }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                SectionTitle("Profile Change Requests")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(0..<statuses.count, id: \.self) { i in
                            Chip(label: statuses[i].1, selected: status == statuses[i].0) { status = statuses[i].0 }
                        }
                    }
                }
                HRField("Search name, field, value", text: $query)
                list
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 24)
        }
        .appBackground()
    }

    private var list: some View {
        let st: String? = status == "all" ? nil : status
        let qq: String = query.trimmingCharacters(in: .whitespaces)
        let q: String? = qq.isEmpty ? nil : qq
        let key: String = "\(status):\(query):\(refresh)"
        return AsyncContent(key: AnyHashable(key), live: true, load: { () async throws -> [ProfileChangeRequest] in
            try await API.shared.changeRequests(status: st, q: q)
        }) { reqs, _ in
            if reqs.isEmpty {
                EmptyState("No requests.")
            } else {
                VStack(spacing: 10) {
                    ForEach(reqs) { r in
                        requestCard(r)
                    }
                }
            }
        }
    }

    private func noteBinding(_ id: Int) -> Binding<String> {
        Binding<String>(get: { notes[id] ?? "" }, set: { notes[id] = $0 })
    }

    private func requestCard(_ r: ProfileChangeRequest) -> some View {
        InfoCard(spacing: 4) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(r.userName ?? "Employee").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
                    Text([r.userCode, r.userBranch].compactMap { $0 }.joined(separator: " · "))
                        .font(.labelSmall).foregroundColor(.Muted)
                }
                Spacer()
                Text(r.status.uppercased()).font(.labelSmall.weight(.semibold)).foregroundColor(CRFmt.statusColor(r.status))
            }
            Text("\(r.fieldLabel ?? r.field):  \(r.oldValue ?? "—")  →  \(r.newValue ?? "")")
                .font(.bodyMedium).foregroundColor(.TextDark)
                .padding(.top, 6)
            if let n = r.note, !n.trimmingCharacters(in: .whitespaces).isEmpty {
                Text("Reason: \(n)").font(.bodySmall).foregroundColor(.Muted)
            }
            footer(r)
        }
    }

    @ViewBuilder private func footer(_ r: ProfileChangeRequest) -> some View {
        if r.status == "pending" {
            HRField("Remark (optional)", text: noteBinding(r.id))
            HStack(spacing: 8) {
                HRFilledButton("Approve & apply", color: .Good, enabled: busyId == nil) { decide(r, approve: true) }
                HROutlinedButton("Reject", enabled: busyId == nil) { decide(r, approve: false) }
            }
            .padding(.top, 6)
        } else if !(r.reviewerName ?? "").isEmpty || !(r.reviewNote ?? "").isEmpty {
            Text(CRFmt.reviewLine(r))
                .font(.labelSmall).foregroundColor(.Muted)
                .padding(.top, 4)
        }
    }

    private func decide(_ r: ProfileChangeRequest, approve: Bool) {
        busyId = r.id
        let note: String? = notes[r.id]
        Task { @MainActor in
            do {
                _ = try await API.shared.decideChangeRequest(id: r.id, approve: approve, reviewNote: note)
            } catch {
                app.toast(error.localizedDescription)
            }
            notes.removeValue(forKey: r.id)
            refresh += 1
            busyId = nil
        }
    }
}

enum CRFmt {
    /// Kotlin listOfNotNull(reviewerName?.let { "by $it" }, reviewNote).joinToString(" · ")
    static func reviewLine(_ r: ProfileChangeRequest) -> String {
        var parts: [String] = []
        if let n = r.reviewerName { parts.append("by " + n) }
        if let note = r.reviewNote { parts.append(note) }
        return parts.joined(separator: " · ")
    }

    static func statusColor(_ s: String) -> Color {
        switch s {
        case "approved": return .Good
        case "rejected": return .Bad
        default: return .BrandBlue
        }
    }
}
