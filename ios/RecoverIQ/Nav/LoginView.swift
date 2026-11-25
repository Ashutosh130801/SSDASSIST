import SwiftUI

/// Port of ui/LoginScreen.kt (email + password, 2FA code when the server asks for it).
struct LoginView: View {
    @EnvironmentObject var app: AppState
    @State private var email: String = ""
    @State private var password: String = ""
    @State private var otp: String = ""

    private var canSubmit: Bool {
        !app.busy && !email.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Spacer(minLength: 60)
                logo
                Text("RecoverIQ").font(.system(size: 24, weight: .bold)).foregroundColor(.TextDark)
                Text("Collections & Recovery Intelligence")
                    .font(.bodyMedium).foregroundColor(.Muted).multilineTextAlignment(.center)
                Spacer().frame(height: 8)
                fields
                if let e = app.error {
                    Text(e).font(.bodySmall).foregroundColor(.Bad).multilineTextAlignment(.center)
                }
                PrimaryButton(title: "Sign in", busy: app.busy, enabled: canSubmit) {
                    submit()
                }
                .frame(height: 50)
                Text("Device: " + Session.shared.deviceId)
                    .font(.system(size: 10)).foregroundColor(.MutedDim).padding(.top, 8)
            }
            .padding(24)
            .frame(maxWidth: 480)
            .frame(maxWidth: .infinity)
        }
        .appBackground()
    }

    private var logo: some View {
        ZStack {
            Circle().fill(Color.BrandBlue).frame(width: 72, height: 72)
            if UIImage(named: "ssd_logo") != nil {
                Image("ssd_logo").resizable().scaledToFit().frame(width: 72, height: 72).clipShape(Circle())
            } else {
                Text("R").font(.system(size: 34, weight: .bold)).foregroundColor(.white)
            }
        }
    }

    private var fields: some View {
        VStack(spacing: 12) {
            LabeledField(label: "Work email") {
                TextField("name@company.com", text: $email)
                    .keyboardType(.emailAddress)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
            }
            LabeledField(label: "Password") {
                SecureField("Password", text: $password)
                    .textContentType(.password)
                    .submitLabel(.go)
                    .onSubmit { if canSubmit { submit() } }
            }
            if app.needsOtp {
                LabeledField(label: "2FA code") {
                    TextField("6-digit code", text: $otp)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .onChange(of: otp) { v in
                            let digits = String(v.filter { $0.isNumber }.prefix(6))
                            if digits != v { otp = digits }
                        }
                }
            }
        }
    }

    private func submit() {
        let code = otp.trimmingCharacters(in: .whitespaces)
        app.login(email: email, password: password, otp: code.isEmpty ? nil : code)
    }
}

/// Outlined text-field look (Compose OutlinedTextField with a label).
struct LabeledField<Content: View>: View {
    let label: String
    let content: Content

    init(label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.labelMedium).foregroundColor(.Muted)
            content
                .font(.bodyLarge)
                .padding(.horizontal, 12).padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
        }
    }
}
