import SwiftUI

// Port of ChatPanel (ui/common/CollabScreens.kt): conversation list (search), new-chat contact picker
// (search + role filter + locked/request-to-chat), broadcast to selected people, and the thread view.

/// Which conversation is open: `withId == nil && office == true` → office desk broadcast thread.
struct ChatTarget: Equatable {
    let withId: Int?
    let office: Bool
}

private func chatMatches(_ c: [String: JSONValue], _ term: String) -> Bool {
    if term.isEmpty { return true }
    return c["name"].cs.lowercased().contains(term) || c["emp_code"].cs.lowercased().contains(term)
}

struct ChatPanel: View {
    let user: User
    let onClose: () -> Void

    @State private var active: ChatTarget? = nil
    @State private var activeName: String = ""
    @State private var activeRole: String = ""
    @State private var picker: Bool = false
    @State private var bcast: Bool = false
    @State private var query: String = ""      // conversation-list search
    @State private var pq: String = ""         // picker search
    @State private var roleF: String = ""
    @State private var reload: Int = 0         // bump to refetch contacts
    @State private var bsel: Set<Int> = []     // broadcast recipients
    @State private var btext: String = ""
    @State private var bq: String = ""
    @State private var sending: Bool = false

    private var canBroadcast: Bool {
        ["admin", "manager", "headoffice", "teamlead", "backend", "hr"].contains(user.role)
    }

    private func openChat(_ id: Int?, _ office: Bool, _ name: String, _ role: String) {
        active = ChatTarget(withId: id, office: office)
        activeName = name
        activeRole = role
        picker = false
        bcast = false
    }

    private func requestChat(_ id: Int) {
        Task {
            _ = try? await API.shared.chatRequest(toId: id)
            reload += 1
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let a = active {
                threadHeader(a)
                ChatThreadView(withId: a.withId, office: a.office)
            } else if picker {
                pickerView
            } else if bcast {
                broadcastView
            } else {
                listView
            }
        }
        .background(Color.CardWhite)
    }

    // MARK: thread header

    private func threadHeader(_ a: ChatTarget) -> some View {
        ChatHeaderBar(onBack: { active = nil; reload += 1 }) {
            ChatAvatar(name: activeName, office: a.office, small: true)
            VStack(alignment: .leading, spacing: 1) {
                Text(activeName).font(.system(size: 14, weight: .bold)).foregroundColor(.white).lineLimit(1)
                Text(activeRole).font(.system(size: 10.5)).foregroundColor(Color.white.opacity(0.85)).lineLimit(1)
            }
        }
    }

    // MARK: conversation list

    private var listView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 14) {
                Text("Chats").font(.system(size: 18, weight: .bold)).foregroundColor(.white)
                Spacer()
                if canBroadcast {
                    Button(action: { bcast = true }) { Text("📢").font(.system(size: 17)) }.buttonStyle(.plain)
                }
                Button(action: onClose) { Text("✕").font(.system(size: 16)).foregroundColor(.white) }.buttonStyle(.plain)
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(WaColor.header)
            ChatSearchField(placeholder: "Search chats", text: $query)
            ZStack(alignment: .bottomTrailing) {
                WaColor.bg
                AsyncContent(key: AnyHashable(reload), load: { try await API.shared.chatContacts() }) { (d: [String: JSONValue], _: @escaping () -> Void) in
                    ChatConversationList(d: d, query: query, onOpen: openChat)
                }
                Button(action: { picker = true }) {
                    Text("✎").font(.system(size: 22)).foregroundColor(.white)
                        .frame(width: 56, height: 56)
                        .background(Circle().fill(WaColor.header))
                        .shadow(color: Color.black.opacity(0.2), radius: 5, x: 0, y: 2)
                }
                .buttonStyle(.plain)
                .padding(16)
            }
        }
    }

    // MARK: new chat picker

    private var pickerView: some View {
        VStack(spacing: 0) {
            ChatHeaderBar(onBack: { picker = false; pq = ""; roleF = "" }) {
                Text("Select contact").font(.system(size: 15, weight: .bold)).foregroundColor(.white)
            }
            ChatSearchField(placeholder: "Search name or ID…", text: $pq)
            AsyncContent(key: AnyHashable(reload), load: { try await API.shared.chatContacts() }) { (d: [String: JSONValue], _: @escaping () -> Void) in
                ChatPickerList(d: d, pq: pq, roleF: $roleF, onOpen: openChat, onRequest: requestChat)
            }
        }
    }

    // MARK: broadcast

    private var broadcastTitle: String {
        "📢 Broadcast" + (bsel.isEmpty ? "" : " · \(bsel.count) selected")
    }

    private var broadcastView: some View {
        VStack(spacing: 0) {
            ChatHeaderBar(onBack: { bcast = false; bq = "" }) {
                Text(broadcastTitle).font(.system(size: 15, weight: .bold)).foregroundColor(.white)
            }
            ChatSearchField(placeholder: "Search people…", text: $bq)
            ZStack {
                WaColor.bg
                AsyncContent(load: { try await API.shared.chatContacts() }) { (d: [String: JSONValue], _: @escaping () -> Void) in
                    ChatBroadcastList(d: d, bq: bq, bsel: $bsel)
                }
            }
            broadcastComposer
        }
    }

    private var broadcastComposer: some View {
        let ready: Bool = !btext.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !bsel.isEmpty
        let who: String = bsel.count == 1 ? "person" : "people"
        return VStack(spacing: 6) {
            TextField("Broadcast message…", text: $btext, axis: .vertical)
                .lineLimit(1...3)
                .padding(.horizontal, 12).padding(.vertical, 9)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
            PrimaryButton(title: "Send to \(bsel.count) \(who)", busy: sending, enabled: ready, color: WaColor.header) {
                sendBroadcast()
            }
        }
        .padding(8)
        .background(WaColor.bar)
    }

    private func sendBroadcast() {
        let t: String = btext.trimmingCharacters(in: .whitespacesAndNewlines)
        let ids: [Int] = Array(bsel)
        if t.isEmpty || ids.isEmpty { return }
        sending = true
        Task {
            _ = try? await API.shared.chatBroadcast(toIds: ids, body: t)
            sending = false
            bcast = false
            bsel = []
            btext = ""
            bq = ""
        }
    }
}

// MARK: - Conversation list body

private struct ChatConversationList: View {
    let d: [String: JSONValue]
    let query: String
    let onOpen: (Int?, Bool, String, String) -> Void

    var body: some View {
        let contacts: [[String: JSONValue]] = d["contacts"].cl.map { $0.cm }
        let office: [String: JSONValue] = d["office"].cm
        let term: String = query.trimmingCharacters(in: .whitespaces).lowercased()
        let convos: [[String: JSONValue]] = contacts.filter { c in
            let at: String = c["last_at"].cStr ?? ""
            return !at.trimmingCharacters(in: .whitespaces).isEmpty
                && (term.isEmpty || c["name"].cs.lowercased().contains(term))
        }
        let officeAt: String? = office["last_at"].cStr
        let hasOffice: Bool = !(officeAt ?? "").trimmingCharacters(in: .whitespaces).isEmpty
        ScrollView {
            LazyVStack(spacing: 0) {
                if hasOffice {
                    ChatConvRow(name: "Office desk", office: true, last: office["last"].cs, at: officeAt,
                                unread: 0, sub: "Office broadcast") {
                        onOpen(nil, true, "Office desk", "Office broadcast")
                    }
                }
                if convos.isEmpty && !hasOffice {
                    Text("No conversations yet.\nTap the pencil button to start a chat.")
                        .font(.system(size: 13)).foregroundColor(.Muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(20)
                }
                ForEach(0..<convos.count, id: \.self) { i in
                    let c: [String: JSONValue] = convos[i]
                    let role: String = collabRoleLabel(c["role"].cs)
                    ChatConvRow(name: c["name"].cs, office: false, last: c["last"].cs, at: c["last_at"].cStr,
                                unread: c["unread"].ci, sub: role) {
                        onOpen(c["id"].ci, false, c["name"].cs, role)
                    }
                }
            }
            .padding(.bottom, 90)
        }
    }
}

// MARK: - Contact picker body

private struct ChatPickerList: View {
    let d: [String: JSONValue]
    let pq: String
    @Binding var roleF: String
    let onOpen: (Int?, Bool, String, String) -> Void
    let onRequest: (Int) -> Void

    var body: some View {
        let contacts: [[String: JSONValue]] = d["contacts"].cl.map { $0.cm }
        let roles: [String] = d["roles"].cl.map { $0.text }
        let office: [String: JSONValue] = d["office"].cm
        let term: String = pq.trimmingCharacters(in: .whitespaces).lowercased()
        let list: [[String: JSONValue]] = contacts.filter { c in
            (roleF.isEmpty || c["role"].cs == roleF) && chatMatches(c, term)
        }
        VStack(spacing: 0) {
            if !roles.isEmpty {
                roleChips(roles)
            }
            ScrollView {
                LazyVStack(spacing: 0) {
                    ChatConvRow(name: "Office desk", office: true, last: office["last"].cs, at: nil, unread: 0,
                                sub: "Broadcast to the whole office") {
                        onOpen(nil, true, "Office desk", "Office broadcast")
                    }
                    if list.isEmpty {
                        Text(!term.isEmpty || !roleF.isEmpty ? "No one matches that search." : "No contacts in your scope yet.")
                            .font(.system(size: 12)).foregroundColor(.Muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(14)
                    }
                    ForEach(0..<list.count, id: \.self) { i in
                        ChatPickerRow(c: list[i], onOpen: onOpen, onRequest: onRequest)
                    }
                }
                .padding(.bottom, 40)
            }
        }
    }

    private func roleChips(_ roles: [String]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Chip(label: "All", selected: roleF.isEmpty) { roleF = "" }
                ForEach(0..<roles.count, id: \.self) { i in
                    Chip(label: collabRoleLabel(roles[i]), selected: roleF == roles[i]) { roleF = roles[i] }
                }
            }
            .padding(.horizontal, 8)
        }
        .padding(.bottom, 4)
    }
}

private struct ChatPickerRow: View {
    let c: [String: JSONValue]
    let onOpen: (Int?, Bool, String, String) -> Void
    let onRequest: (Int) -> Void

    private var subline: String {
        let code: String = c["emp_code"].cs
        return collabRoleLabel(c["role"].cs) + (code.trimmingCharacters(in: .whitespaces).isEmpty ? "" : " · \(code)")
    }

    var body: some View {
        let locked: Bool = c["locked"].cTrue
        let pend: Bool = c["pending"].cTrue
        Button(action: {
            if locked {
                if !pend { onRequest(c["id"].ci) }
            } else {
                onOpen(c["id"].ci, false, c["name"].cs, collabRoleLabel(c["role"].cs))
            }
        }) {
            HStack(spacing: 12) {
                ChatAvatar(name: c["name"].cs)
                VStack(alignment: .leading, spacing: 1) {
                    Text(c["name"].cs).fontWeight(.semibold).foregroundColor(WaColor.ink).lineLimit(1)
                    Text(subline).font(.system(size: 11.5)).foregroundColor(.Muted).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if locked {
                    Text(pend ? "⏳ Requested" : "🔒 Request")
                        .font(.system(size: 11.5, weight: .bold))
                        .foregroundColor(pend ? .Warn : WaColor.header)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Broadcast picker body

private struct ChatBroadcastList: View {
    let d: [String: JSONValue]
    let bq: String
    @Binding var bsel: Set<Int>

    var body: some View {
        let term: String = bq.trimmingCharacters(in: .whitespaces).lowercased()
        let list: [[String: JSONValue]] = d["contacts"].cl.map { $0.cm }.filter { c in
            !c["locked"].cTrue && chatMatches(c, term)
        }
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(0..<list.count, id: \.self) { i in
                    row(list[i])
                }
            }
        }
    }

    private func toggle(_ id: Int) {
        if bsel.contains(id) { bsel.remove(id) } else { bsel.insert(id) }
    }

    private func row(_ c: [String: JSONValue]) -> some View {
        let id: Int = c["id"].ci
        let on: Bool = bsel.contains(id)
        return Button(action: { toggle(id) }) {
            HStack(spacing: 10) {
                Image(systemName: on ? "checkmark.square.fill" : "square")
                    .font(.system(size: 20))
                    .foregroundColor(on ? WaColor.header : .MutedDim)
                ChatAvatar(name: c["name"].cs, small: true)
                VStack(alignment: .leading, spacing: 1) {
                    Text(c["name"].cs).fontWeight(.semibold).foregroundColor(WaColor.ink).lineLimit(1)
                    Text(collabRoleLabel(c["role"].cs)).font(.system(size: 11)).foregroundColor(.Muted).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(on ? WaColor.selected : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
