import SwiftUI

/// First login with the shared starter password: force a change before anything else
/// (ProfileScreen.kt ForcePasswordChangeScreen).
struct ForcePasswordChangeView: View {
    @EnvironmentObject var app: AppState
    let onChanged: () -> Void

    @State private var current: String = ""
    @State private var next: String = ""
    @State private var confirm: String = ""
    @State private var busy: Bool = false
    @State private var err: String? = nil

    init(onChanged: @escaping () -> Void) { self.onChanged = onChanged }

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                Spacer().frame(height: 24)
                Text("Set a new password").font(.system(size: 24, weight: .bold)).foregroundColor(.TextDark)
                Text("For your security, please replace the starter password before continuing.")
                    .font(.bodyMedium).foregroundColor(.Muted).multilineTextAlignment(.center)
                LabeledField(label: "Current (starter) password") {
                    SecureField("", text: $current).textContentType(.password)
                }
                LabeledField(label: "New password") {
                    SecureField("", text: $next).textContentType(.newPassword)
                }
                LabeledField(label: "Confirm new password") {
                    SecureField("", text: $confirm).textContentType(.newPassword)
                }
                if let e = err {
                    Text(e).font(.bodySmall).foregroundColor(.Bad)
                }
                PrimaryButton(title: busy ? "Saving…" : "Continue", busy: busy) { submit() }
                Button("Sign out") { app.logout() }.foregroundColor(.Muted).padding(.top, 4)
            }
            .padding(24)
            .frame(maxWidth: 480)
            .frame(maxWidth: .infinity)
        }
        .appBackground()
    }

    private func submit() {
        if next.count < 6 { err = "New password must be at least 6 characters."; return }
        if next != confirm { err = "New passwords don't match."; return }
        if next == current { err = "New password must be different."; return }
        err = nil
        busy = true
        let cur = current
        let new = next
        Task { @MainActor in
            do {
                let t = try await API.shared.changePassword(current: cur, new: new)
                busy = false
                app.passwordChanged(t)
                onChanged()
            } catch {
                busy = false
                err = "Current password is incorrect."
            }
        }
    }
}
