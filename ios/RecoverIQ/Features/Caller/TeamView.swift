import SwiftUI
import UIKit

/// Port of ui/screens/TeamScreen.kt — team member list with call buttons and an "Add member" FAB/dialog.
struct TeamView: View {
    @State private var refresh: Int = 0
    @State private var showAdd: Bool = false

    init() {}

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            AsyncContent(key: AnyHashable(refresh), load: { try await API.shared.users() }) { users, _ in
                ClrTeamUsersList(users: users)
            }
            .padding(.horizontal, 12)

            Button(action: { showAdd = true }) {
                Label("Add member", systemImage: "plus")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 18).padding(.vertical, 14)
                    .background(RoundedRectangle(cornerRadius: 16).fill(Color.BrandBlue))
                    .shadow(color: Color.black.opacity(0.18), radius: 6, x: 0, y: 3)
            }
            .buttonStyle(.plain)
            .padding(16)
        }
        .sheet(isPresented: $showAdd) {
            ClrAddMemberSheet(onDismiss: { showAdd = false }, onConfirm: { (newUser: UserCreate) in
                Task {
                    _ = try? await API.shared.createUser(body: newUser)
                    showAdd = false
                    refresh += 1
                }
            })
        }
    }
}

private struct ClrTeamUsersList: View {
    let users: [User]

    var body: some View {
        if users.isEmpty {
            EmptyState(text: "No team members.")
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(users) { u in
                        ClrTeamMemberRow(u: u)
                    }
                }
                .padding(.top, 12).padding(.bottom, 90)
            }
        }
    }
}

private struct ClrTeamMemberRow: View {
    let u: User

    var body: some View {
        InfoCard {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(u.name).fontWeight(.semibold)
                    Text(u.email).font(.bodySmall).foregroundColor(.Muted)
                    HStack(spacing: 6) {
                        assist(u.roleLabel)
                        if let b = u.branch { assist(b) }
                    }
                    .padding(.top, 4)
                }
                Spacer()
                if let p = u.phone, !p.trimmingCharacters(in: .whitespaces).isEmpty {
                    Button(action: { Actions.dial(p) }) {
                        Image(systemName: "phone.fill")
                            .foregroundColor(u.isActive ? .Good : .Muted)
                            .frame(width: 40, height: 40)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Call")
                }
            }
        }
    }

    private func assist(_ text: String) -> some View {
        Text(text)
            .font(.labelMedium)
            .foregroundColor(.TextDark)
            .lineLimit(1)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.StrokeSoft, lineWidth: 1))
    }
}

private struct ClrAddMemberSheet: View {
    let onDismiss: () -> Void
    let onConfirm: (UserCreate) -> Void

    @State private var name: String = ""
    @State private var email: String = ""
    @State private var phone: String = ""
    @State private var password: String = ""
    @State private var branch: String = ""
    @State private var role: String = "telecaller"

    private let roles: [String] = ["telecaller", "fos", "manager", "admin"]

    private var canCreate: Bool {
        let n = name.trimmingCharacters(in: .whitespaces)
        let e = email.trimmingCharacters(in: .whitespaces)
        let p = password.trimmingCharacters(in: .whitespaces)
        return !n.isEmpty && !e.isEmpty && !p.isEmpty
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    field("Full name", text: $name)
                    field("Work email", text: $email, keyboard: .emailAddress)
                    field("Phone", text: $phone, keyboard: .phonePad)
                    field("Temp password", text: $password)
                    field("Branch", text: $branch)
                    Text("Role").font(.labelSmall).foregroundColor(.Muted).padding(.top, 4)
                    FlowLayout(spacing: 6) {
                        ForEach(roles, id: \.self) { r in
                            Chip(label: r, selected: role == r) { role = r }
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle("Add team member")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onDismiss)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create", action: create).disabled(!canCreate)
                }
            }
        }
    }

    private func create() {
        let ph: String? = phone.trimmingCharacters(in: .whitespaces).isEmpty ? nil : phone
        let br: String? = branch.trimmingCharacters(in: .whitespaces).isEmpty ? nil : branch
        onConfirm(UserCreate(name: name, email: email.trimmingCharacters(in: .whitespaces).lowercased(),
                             password: password, role: role, phone: ph, branch: br))
    }

    private func field(_ label: String, text: Binding<String>, keyboard: UIKeyboardType = .default) -> some View {
        let cap: TextInputAutocapitalization = (keyboard == .default) ? TextInputAutocapitalization.sentences : TextInputAutocapitalization.never
        return TextField(label, text: text)
            .keyboardType(keyboard)
            .textInputAutocapitalization(cap)
            .disableAutocorrection(true)
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
    }
}
