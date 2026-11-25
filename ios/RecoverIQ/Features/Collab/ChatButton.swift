import SwiftUI

// Port of ChatFab (ui/common/CollabScreens.kt) — floating 💬 button with an unread badge
// (polled every 15 s) that opens the WhatsApp-style team chat in a bottom sheet.

struct ChatButton: View {
    init() {}

    @EnvironmentObject var app: AppState
    @State private var open: Bool = false
    @State private var unread: Int = 0

    var body: some View {
        Button(action: { open = true }) {
            Text("💬")
                .font(.system(size: 22))
                .frame(width: 56, height: 56)
                .background(Circle().fill(Color.BrandBlue))
                .shadow(color: Color.black.opacity(0.2), radius: 6, x: 0, y: 3)
        }
        .buttonStyle(.plain)
        .overlay(badge, alignment: .topTrailing)
        .accessibilityLabel("Team chat")
        .task {
            while !Task.isCancelled {
                await refreshUnread()
                try? await Task.sleep(nanoseconds: 15_000_000_000)
            }
        }
        .sheet(isPresented: $open, onDismiss: { Task { await refreshUnread() } }) {
            sheetContent
        }
    }

    @ViewBuilder private var badge: some View {
        if unread > 0 {
            Text(String(unread))
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.white)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Capsule().fill(Color.Bad))
                .offset(x: 4, y: -4)
        }
    }

    @ViewBuilder private var sheetContent: some View {
        if let u = app.user {
            ChatPanel(user: u, onClose: { open = false })
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        } else {
            EmptyState(text: "Not signed in")
        }
    }

    private func refreshUnread() async {
        do {
            let n: Int = try await API.shared.chatUnread()
            unread = n
        } catch {
            // ignore — Kotlin swallows the error and keeps the last count
        }
    }
}

// MARK: - WhatsApp palette (kept local so the chat looks like WhatsApp regardless of the app theme)

enum WaColor {
    static let header = Color(argb: 0xFF008069)
    static let teal = Color(argb: 0xFF075E54)
    static let outBubble = Color(argb: 0xFFD9FDD3)
    static let bg = Color(argb: 0xFFEFEAE2)
    static let ink = Color(argb: 0xFF111B21)
    static let bar = Color(argb: 0xFFF0F2F5)
    static let green = Color(argb: 0xFF25D366)
    static let tickRead = Color(argb: 0xFF53BDEB)
    static let tickSent = Color(argb: 0xFF8696A0)
    static let hint = Color(argb: 0xFF667781)
    static let avatarBg = Color(argb: 0xFFDFE5E7)
    static let avatarFg = Color(argb: 0xFF5B6B72)
    static let selected = Color(argb: 0x1400A884)
}

struct ChatAvatar: View {
    let name: String
    var office: Bool = false
    var small: Bool = false

    private var initial: String {
        let t = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return "?" }
        return String(t.prefix(1)).uppercased()
    }

    var body: some View {
        let sz: CGFloat = small ? 34 : 44
        ZStack {
            Circle().fill(office ? WaColor.teal : WaColor.avatarBg)
            Text(office ? "🏢" : initial)
                .font(.system(size: small ? 15 : 18, weight: .bold))
                .foregroundColor(office ? .white : WaColor.avatarFg)
        }
        .frame(width: sz, height: sz)
    }
}

/// One conversation row (Kotlin ConvRow).
struct ChatConvRow: View {
    let name: String
    let office: Bool
    let last: String
    let at: String?
    let unread: Int
    let sub: String
    let onClick: () -> Void

    var body: some View {
        Button(action: onClick) {
            HStack(spacing: 12) {
                ChatAvatar(name: name, office: office)
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(name).fontWeight(.semibold).foregroundColor(WaColor.ink).lineLimit(1)
                        Spacer(minLength: 4)
                        if let a = at, !a.isEmpty {
                            Text(chatWhen(a))
                                .font(.system(size: 10, weight: unread > 0 ? .bold : .regular))
                                .foregroundColor(unread > 0 ? WaColor.header : .Muted)
                        }
                    }
                    HStack {
                        Text(last.trimmingCharacters(in: .whitespaces).isEmpty ? sub : last)
                            .font(.system(size: 12.5)).foregroundColor(.Muted).lineLimit(1)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        if unread > 0 {
                            Text(String(unread))
                                .font(.system(size: 10, weight: .bold)).foregroundColor(.white)
                                .padding(.horizontal, 6).padding(.vertical, 1)
                                .background(Capsule().fill(WaColor.green))
                        }
                    }
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Green header bar with a back chevron and a title (used by picker / broadcast / thread).
struct ChatHeaderBar<Trailing: View>: View {
    let onBack: () -> Void
    let trailing: Trailing

    init(onBack: @escaping () -> Void, @ViewBuilder trailing: () -> Trailing) {
        self.onBack = onBack
        self.trailing = trailing()
    }

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onBack) {
                Text("‹").font(.system(size: 28)).foregroundColor(.white).frame(width: 28, height: 32)
            }
            .buttonStyle(.plain)
            trailing
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(WaColor.header)
    }
}

/// Search box with a 🔍 leading icon (OutlinedTextField + leadingIcon).
struct ChatSearchField: View {
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: 6) {
            Text("🔍")
            TextField(placeholder, text: $text)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
            if !text.isEmpty {
                Button(action: { text = "" }) {
                    Image(systemName: "xmark.circle.fill").foregroundColor(.MutedDim)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
        .padding(8)
    }
}
