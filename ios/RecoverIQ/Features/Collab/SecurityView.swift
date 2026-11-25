import SwiftUI
import UIKit

// Port of ui/screens/SecurityScreen.kt — account card + TOTP two-factor setup (QR + key → verify) / disable.

struct SecurityView: View {
    init() {}

    @EnvironmentObject var app: AppState

    @State private var refresh: Int = 0
    @State private var setup: TwoFASetup? = nil
    @State private var otp: String = ""
    @State private var msg: String? = nil
    @State private var busy: Bool = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                SectionTitle("Security")
                if let u = app.user {
                    InfoCard {
                        Text(u.name).fontWeight(.semibold).foregroundColor(.TextDark)
                        Text(u.email).font(.bodySmall).foregroundColor(.Muted)
                        Text(u.roleLabel).font(.bodySmall).foregroundColor(.Muted)
                    }
                }
                AsyncContent(key: AnyHashable(refresh), load: { try await API.shared.twoFAStatus() }) { (status: TwoFAStatus, _: @escaping () -> Void) in
                    twoFACard(status)
                }
                .frame(minHeight: 160)
            }
            .padding(16)
            .padding(.bottom, 120)
        }
    }

    // MARK: 2FA card

    private func twoFACard(_ status: TwoFAStatus) -> some View {
        InfoCard {
            Text("Two-factor authentication").fontWeight(.semibold).foregroundColor(.TextDark)
            Text(status.enabled ? "Enabled — your account asks for a code at sign-in."
                                : "Add an authenticator app for an extra layer of security.")
                .font(.bodySmall)
                .foregroundColor(status.enabled ? .Good : .Muted)
            Spacer().frame(height: 8)
            if status.enabled {
                enabledSection
            } else if let s = setup {
                setupSection(s)
            } else {
                PrimaryButton(title: "Set up 2FA", busy: busy) { startSetup() }
            }
            if let m = msg {
                Text(m).font(.bodySmall).foregroundColor(.Good).padding(.top, 8)
            }
        }
    }

    private var enabledSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            otpField("Current 6-digit code")
            PrimaryButton(title: "Disable 2FA", busy: busy, color: .Bad) { disable() }
        }
    }

    private func setupSection(_ s: TwoFASetup) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("1. Scan this QR in Google Authenticator (or enter the key).")
                .font(.bodySmall).foregroundColor(.Muted)
            HStack {
                Spacer()
                QrImage(content: s.otpauthUrl, size: 200)
                Spacer()
            }
            .padding(.vertical, 8)
            HStack(spacing: 6) {
                Text("Key: \(s.secret)").font(.labelSmall).foregroundColor(.Muted).textSelection(.enabled)
                Button(action: {
                    UIPasteboard.general.string = s.secret
                    app.toast("Key copied")
                }) {
                    Image(systemName: "doc.on.doc").font(.system(size: 12)).foregroundColor(.BrandBlue)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Copy key")
            }
            otpField("2. Enter the 6-digit code").padding(.top, 8)
            PrimaryButton(title: "Verify & enable", busy: busy) { enable() }
            Button(action: { setup = nil; otp = "" }) {
                Text("Cancel").fontWeight(.semibold).foregroundColor(.BrandBlue)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.StrokeSoft, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
    }

    private func otpField(_ label: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.labelSmall).foregroundColor(.Muted)
            TextField("123456", text: $otp)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
                .onChange(of: otp) { v in
                    let f: String = String(v.filter { $0.isNumber }.prefix(6))
                    if f != v { otp = f }
                }
        }
    }

    // MARK: actions

    private func startSetup() {
        busy = true
        Task {
            let s: TwoFASetup? = try? await API.shared.twoFASetup()
            setup = s
            busy = false
        }
    }

    private func enable() {
        let code: String = otp
        busy = true
        Task {
            do {
                _ = try await API.shared.twoFAEnable(otp: code)
                msg = "2FA enabled."
                setup = nil
                otp = ""
                refresh += 1
            } catch {
                msg = "Incorrect code — try again."
            }
            busy = false
        }
    }

    private func disable() {
        let code: String = otp
        busy = true
        Task {
            do {
                _ = try await API.shared.twoFADisable(otp: code)
                msg = "2FA disabled."
            } catch {
                msg = "Incorrect code."
            }
            otp = ""
            refresh += 1
            busy = false
        }
    }
}
