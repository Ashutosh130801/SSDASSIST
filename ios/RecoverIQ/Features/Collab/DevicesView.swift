import SwiftUI

// Port of ui/screens/DevicesScreen.kt — registered devices with multi-word search, approve / revoke.

struct DevicesView: View {
    init() {}

    @State private var refresh: Int = 0
    @State private var query: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Registered devices")
                .padding(.top, 12).padding(.leading, 4)
            searchField.padding(.vertical, 8)
            AsyncContent(key: AnyHashable(refresh), load: { try await API.shared.devices() }) { (all: [Device], _: @escaping () -> Void) in
                DeviceList(all: all, query: query, onApprove: approve, onRevoke: revoke)
            }
        }
        .padding(.horizontal, 12)
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(.Muted)
            TextField("Search name, employee ID, branch or device", text: $query)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
            if !query.isEmpty {
                Button(action: { query = "" }) {
                    Image(systemName: "xmark").foregroundColor(.Muted)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear")
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 11)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
    }

    private func approve(_ id: Int) {
        Task {
            try? await API.shared.approveDevice(id: id)
            refresh += 1
        }
    }

    private func revoke(_ id: Int) {
        Task {
            try? await API.shared.revokeDevice(id: id)
            refresh += 1
        }
    }
}

private struct DeviceList: View {
    let all: [Device]
    let query: String
    let onApprove: (Int) -> Void
    let onRevoke: (Int) -> Void

    private var words: [String] {
        query.trimmingCharacters(in: .whitespaces).lowercased()
            .split(whereSeparator: { $0 == " " || $0 == "\t" || $0 == "\n" })
            .map { String($0) }
            .filter { !$0.isEmpty }
    }

    /// All typed words must match (name, emp ID, role, branch, device id, label).
    private var devices: [Device] {
        let w: [String] = words
        if w.isEmpty { return all }
        return all.filter { d in
            let parts: [String?] = [d.userName, d.userCode, d.userRole, d.userBranch, d.deviceId, d.label]
            let hay: String = parts.compactMap { $0 }.joined(separator: " ").lowercased()
            return w.allSatisfy { hay.contains($0) }
        }
    }

    var body: some View {
        let list: [Device] = devices
        if list.isEmpty {
            EmptyState(words.isEmpty ? "No devices registered." : "No devices match \"\(query)\".")
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(list) { d in
                        DeviceCard(d: d, onApprove: { onApprove(d.id) }, onRevoke: { onRevoke(d.id) })
                    }
                }
                .padding(.bottom, 140)
            }
        }
    }
}

private struct DeviceCard: View {
    let d: Device
    let onApprove: () -> Void
    let onRevoke: () -> Void

    var body: some View {
        InfoCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(d.userName ?? "User #\(d.userId)").fontWeight(.semibold).foregroundColor(.TextDark)
                    if let code = d.userCode {
                        Text(code).font(.labelSmall).foregroundColor(.Muted)
                    }
                    Text(d.label ?? d.deviceId).font(.bodySmall).foregroundColor(.Muted)
                    if let b = d.userBranch {
                        Text(b).font(.labelSmall).foregroundColor(.Muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                StatusChip(d.approved ? "approved" : "pending")
            }
            actionButton.padding(.top, 8)
        }
    }

    @ViewBuilder private var actionButton: some View {
        if !d.approved {
            Button(action: onApprove) {
                Text("Approve").fontWeight(.semibold).foregroundColor(.white)
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .background(RoundedRectangle(cornerRadius: 20).fill(Color.Good))
            }
            .buttonStyle(.plain)
        } else {
            Button(action: onRevoke) {
                Text("Revoke").fontWeight(.semibold).foregroundColor(.BrandBlue)
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.StrokeSoft, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
    }
}
