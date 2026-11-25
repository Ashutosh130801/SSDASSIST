import SwiftUI
import UIKit

/// Port of ProfileScreen.kt `ProfileScreen` — "My E-ID": own FTD/MTD/LMTD/Overall strip (field / calling /
/// team-lead staff), the identity card, photo upload, details, one-time self-edit (then locked →
/// change requests to HR/Admin + my request history) and change password.
struct ProfileView: View {
    @EnvironmentObject var app: AppState

    @State private var refresh: Int = 0
    @State private var showPwd: Bool = false
    @State private var trends: Trends? = nil

    init() {}

    private var showsTrends: Bool {
        guard let u = app.user else { return false }
        return u.isFieldAgent || u.isTelecaller || u.isTeamLead
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                SectionTitle("My E-ID")
                if showsTrends, let t = trends {
                    InfoCard { TrendStrip(trends: t, title: "My cash collected — FTD / MTD / LMTD / Overall") }
                }
                AsyncContent(key: AnyHashable(refresh), load: { () async throws -> EmployeeProfile in
                    try await API.shared.myProfile()
                }) { p, reload in
                    profileBody(p, reload: reload)
                }
            }
            .padding(16)
        }
        .appBackground()
        .task {
            if showsTrends {
                trends = (try? await API.shared.myTrends())?.trends
            }
        }
        .sheet(isPresented: $showPwd) {
            ProfileChangePasswordSheet(onDismiss: { showPwd = false })
        }
    }

    @ViewBuilder
    private func profileBody(_ p: EmployeeProfile, reload: @escaping () -> Void) -> some View {
        ProfileEidCard(p: p)
        ProfilePhotoUploadButton(onDone: {
            refresh += 1
            reload()
        })
        ProfileDetailsCard(p: p)
        if !p.profileCompleted {
            ProfileEditDetailsCard(p: p, onSaved: {
                refresh += 1
                reload()
            })
            .id("edit-\(p.id)")
        } else {
            ProfileChangeRequestSection(onChanged: { refresh += 1 })
        }
        passwordCard
    }

    private var passwordCard: some View {
        InfoCard {
            Text("Password").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
            Text("Keep your account secure — change your password regularly.")
                .font(.bodySmall).foregroundColor(.Muted)
            HROutlinedButton("Change password") { showPwd = true }
                .padding(.top, 8)
        }
    }
}

// MARK: - Helpers

enum ProfileFmt {
    static func initials(_ name: String) -> String {
        let parts: [String] = name.trimmingCharacters(in: .whitespaces)
            .split(whereSeparator: { $0 == " " || $0 == "\t" || $0 == "\n" })
            .map { String($0) }
            .filter { !$0.isEmpty }
        let s: String = parts.prefix(2).map { String($0.prefix(1)).uppercased() }.joined()
        return s.isEmpty ? "?" : s
    }

    static func mask(_ v: String?) -> String? {
        guard let raw = v, !raw.trimmingCharacters(in: .whitespaces).isEmpty else { return v }
        let s: String = raw.trimmingCharacters(in: .whitespaces)
        return s.count <= 4 ? s : "•••• " + String(s.suffix(4))
    }

    static func roleTitle(_ role: String) -> String {
        switch role {
        case "fos": return "Field Executive"
        case "telecaller": return "Tele-caller"
        case "teamlead": return "Team Leader"
        case "manager": return "Manager"
        case "headoffice": return "Head Office"
        case "hr": return "HR"
        case "it": return "IT"
        case "admin": return "Administrator"
        default: return role.prefix(1).uppercased() + String(role.dropFirst())
        }
    }
}

// MARK: - E-ID card

struct ProfileEidCard: View {
    let p: EmployeeProfile

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("SSD ENTERPRISES")
                .font(.labelMedium.weight(.bold)).kerning(2)
                .foregroundColor(Color.white.opacity(0.85))
            Text("Employee Identity Card")
                .font(.labelSmall).foregroundColor(Color.white.opacity(0.7))
            HStack(alignment: .center, spacing: 16) {
                avatar
                VStack(alignment: .leading, spacing: 2) {
                    Text(p.name).font(.titleLarge.weight(.bold)).foregroundColor(.white)
                    Text(p.designation ?? ProfileFmt.roleTitle(p.role))
                        .font(.bodyMedium).foregroundColor(Color.white.opacity(0.9))
                    if let code = p.empCode {
                        Text(code).font(.labelLarge.weight(.semibold)).foregroundColor(.white)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.top, 16)
            HStack(alignment: .top) {
                field("Branch", p.branch ?? p.location ?? "—")
                field("Blood Group", p.bloodGroup ?? "—")
            }
            .padding(.top, 16)
            HStack(alignment: .top) {
                field("Phone", p.phone ?? "—")
                field("Joined", p.joiningDate ?? "—")
            }
            .padding(.top, 10)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(LinearGradient(colors: [Color.BrandBlue, Color.BrandBlueDark], startPoint: .top, endPoint: .bottom))
        )
        .shadow(color: Color.black.opacity(0.18), radius: 8, x: 0, y: 4)
    }

    private var avatar: some View {
        ZStack {
            Circle().fill(Color.white.opacity(0.18))
            if let url = Session.absoluteURL(p.photoUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFill()
                    default:
                        initialsText
                    }
                }
            } else {
                initialsText
            }
        }
        .frame(width: 72, height: 72)
        .clipShape(Circle())
    }

    private var initialsText: some View {
        Text(ProfileFmt.initials(p.name))
            .font(.headlineSmall.weight(.bold)).foregroundColor(.white)
    }

    private func field(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label.uppercased()).font(.labelSmall).kerning(1).foregroundColor(Color.white.opacity(0.65))
            Text(value).font(.bodyMedium.weight(.medium)).foregroundColor(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Details

struct ProfileDetailsCard: View {
    let p: EmployeeProfile

    private var rows: [(String, String?)] {
        return [
            ("Email", p.email),
            ("Role", ProfileFmt.roleTitle(p.role)),
            ("Location", p.location),
            ("Gender", p.gender),
            ("Date of birth", p.dob),
            ("Marital status", p.maritalStatus),
            ("Emergency contact", p.emergencyContact),
            ("Emergency name", p.emergencyName),
            ("Aadhaar", ProfileFmt.mask(p.aadharNumber)),
            ("PAN", p.panNumber),
            ("Bank", p.bankName),
            ("Account", ProfileFmt.mask(p.bankAccount)),
            ("IFSC", p.ifscCode),
            ("Address", p.currentAddress),
        ]
    }

    var body: some View {
        let visible: [(String, String)] = rows.compactMap { r in
            guard let v = r.1, !v.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
            return (r.0, v)
        }
        return InfoCard {
            Text("Details").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
                .padding(.bottom, 6)
            ForEach(0..<visible.count, id: \.self) { i in
                HStack(alignment: .top, spacing: 0) {
                    Text(visible[i].0).font(.bodySmall).foregroundColor(.MutedDim)
                        .frame(width: 130, alignment: .leading)
                    Text(visible[i].1).font(.bodyMedium).foregroundColor(.TextDark)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.vertical, 3)
            }
        }
    }
}

// MARK: - Photo upload

struct ProfilePhotoUploadButton: View {
    let onDone: () -> Void

    @EnvironmentObject var app: AppState
    @State private var busy: Bool = false
    @State private var showPicker: Bool = false

    var body: some View {
        HROutlinedButton(busy ? "Uploading…" : "📷 Change photo", enabled: !busy, fill: false) {
            showPicker = true
        }
        .sheet(isPresented: $showPicker) {
            HRImagePicker(source: .library) { img in
                showPicker = false
                if let i = img { upload(i) }
            }
            .ignoresSafeArea()
        }
    }

    private func upload(_ image: UIImage) {
        guard let bytes = HRUtil.scaled(image, maxWidth: 1280).jpegData(compressionQuality: 0.85) else { return }
        busy = true
        Task { @MainActor in
            do {
                _ = try await API.shared.uploadProfilePhoto(bytes: bytes)
                busy = false
                onDone()
            } catch {
                busy = false
                app.toast(error.localizedDescription)
            }
        }
    }
}
