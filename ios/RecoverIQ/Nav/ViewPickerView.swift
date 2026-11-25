import SwiftUI

/// Dual-role "which hat?" picker, shown after login and on Switch view (AppRoot.kt ViewPickerScreen).
struct ViewPickerView: View {
    @EnvironmentObject var app: AppState
    let user: User

    init(user: User) { self.user = user }

    static func viewMeta(_ v: String) -> (icon: String, title: String, sub: String) {
        switch v {
        case "teamlead": return ("👥", "Team Leader", "Your team’s cases, MIS & DPR")
        case "fos": return ("🗺️", "Field Agent", "Your field visits & route")
        case "telecaller": return ("📞", "Tele-calling", "Your calling queue")
        case "manager": return ("🏢", "Manager", "Branch overview")
        case "headoffice": return ("🏛️", "Head Office", "All portfolios")
        case "admin": return ("🛡️", "Administrator", "Full access")
        default: return ("•", v, "")
        }
    }

    private var firstName: String {
        String(user.name.split(separator: " ").first ?? Substring(user.name))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Spacer().frame(height: 24)
                Text("Choose your view").font(.system(size: 24, weight: .bold)).foregroundColor(.BrandBlue)
                Text("Hi \(firstName) — you have more than one role. Pick how to work now; you can switch anytime.")
                    .font(.bodyMedium).foregroundColor(.Muted)
                ForEach(user.availableViews, id: \.self) { v in
                    viewCard(v)
                }
                HStack {
                    if app.pickView && app.user != nil {
                        Button("Cancel") { app.pickView = false }.foregroundColor(.BrandBlue)
                    }
                    Spacer()
                    Button("Sign out") { app.logout() }.foregroundColor(.Bad)
                }
                .padding(.top, 8)
            }
            .padding(24)
        }
        .appBackground()
    }

    private func viewCard(_ v: String) -> some View {
        let meta = ViewPickerView.viewMeta(v)
        let current = v == user.activeView
        return Button(action: { app.switchView(v) }) {
            HStack(spacing: 14) {
                Text(meta.icon).font(.system(size: 28))
                VStack(alignment: .leading, spacing: 2) {
                    Text(meta.title + (current ? "  ·  current" : "")).font(.system(size: 15, weight: .bold)).foregroundColor(.TextDark)
                    Text(meta.sub).font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer()
                Text("→").foregroundColor(.Muted)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 16).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(current ? Color.BrandBlue.opacity(0.5) : Color.GlassStroke, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
