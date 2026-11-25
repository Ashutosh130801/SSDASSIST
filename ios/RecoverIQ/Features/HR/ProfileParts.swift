import SwiftUI

// ProfileScreen.kt sub-parts: one-time self-edit, locked-profile change requests, change password.

// MARK: - One-time self edit ("Save & lock")

struct ProfileEditDetailsCard: View {
    let p: EmployeeProfile
    let onSaved: () -> Void

    @State private var phone: String = ""
    @State private var gender: String = ""
    @State private var dob: String = ""
    @State private var blood: String = ""
    @State private var marital: String = ""
    @State private var emgContact: String = ""
    @State private var emgName: String = ""
    @State private var emgRel: String = ""
    @State private var aadhar: String = ""
    @State private var pan: String = ""
    @State private var bankHolder: String = ""
    @State private var bankAccount: String = ""
    @State private var ifsc: String = ""
    @State private var bankName: String = ""
    @State private var address: String = ""
    @State private var busy: Bool = false
    @State private var msg: String? = nil

    init(p: EmployeeProfile, onSaved: @escaping () -> Void) {
        self.p = p
        self.onSaved = onSaved
        _phone = State(initialValue: p.phone ?? "")
        _gender = State(initialValue: p.gender ?? "")
        _dob = State(initialValue: p.dob ?? "")
        _blood = State(initialValue: p.bloodGroup ?? "")
        _marital = State(initialValue: p.maritalStatus ?? "")
        _emgContact = State(initialValue: p.emergencyContact ?? "")
        _emgName = State(initialValue: p.emergencyName ?? "")
        _emgRel = State(initialValue: p.emergencyRelation ?? "")
        _aadhar = State(initialValue: p.aadharNumber ?? "")
        _pan = State(initialValue: p.panNumber ?? "")
        _bankHolder = State(initialValue: p.bankHolder ?? "")
        _bankAccount = State(initialValue: p.bankAccount ?? "")
        _ifsc = State(initialValue: p.ifscCode ?? "")
        _bankName = State(initialValue: p.bankName ?? "")
        _address = State(initialValue: p.currentAddress ?? "")
    }

    var body: some View {
        InfoCard(spacing: 6) {
            Text("Complete your profile").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
            Text("You can fill this once. Review carefully — it locks after saving.")
                .font(.bodySmall).foregroundColor(.Muted)
                .padding(.bottom, 4)
            personalFields
            bankFields
            if let m = msg {
                Text(m).font(.bodySmall).foregroundColor(m.hasPrefix("Saved") ? .Good : .Bad)
            }
            HRFilledButton(busy ? "Saving…" : "Save & lock", enabled: !busy) { save() }
                .padding(.top, 8)
        }
    }

    private var personalFields: some View {
        VStack(alignment: .leading, spacing: 8) {
            HRField("Phone", text: $phone, keyboard: .phonePad)
            HRField("Gender", text: $gender)
            HRField("Date of birth (YYYY-MM-DD)", text: $dob, keyboard: .numbersAndPunctuation)
            HRField("Blood group", text: $blood)
            HRField("Marital status", text: $marital)
            HRField("Emergency contact", text: $emgContact, keyboard: .phonePad)
            HRField("Emergency name", text: $emgName)
            HRField("Emergency relation", text: $emgRel)
        }
    }

    private var bankFields: some View {
        VStack(alignment: .leading, spacing: 8) {
            HRField("Aadhaar number", text: $aadhar, keyboard: .numberPad)
            HRField("PAN number", text: $pan)
            HRField("Bank account holder", text: $bankHolder)
            HRField("Bank account number", text: $bankAccount, keyboard: .numberPad)
            HRField("IFSC code", text: $ifsc)
            HRField("Bank name", text: $bankName)
            HRField("Current address", text: $address, multiline: true)
        }
    }

    private func save() {
        busy = true
        msg = nil
        let all: [(String, String)] = [
            ("phone", phone), ("gender", gender), ("dob", dob),
            ("blood_group", blood), ("marital_status", marital),
            ("emergency_contact", emgContact), ("emergency_name", emgName),
            ("emergency_relation", emgRel), ("aadhar_number", aadhar),
            ("pan_number", pan), ("bank_holder", bankHolder),
            ("bank_account", bankAccount), ("ifsc_code", ifsc),
            ("bank_name", bankName), ("current_address", address),
        ]
        var patch: [String: String?] = [:]
        for (k, v) in all where !v.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            patch.updateValue(v, forKey: k)
        }
        Task { @MainActor in
            do {
                try await API.shared.updateMyProfile(patch: patch)
                busy = false
                msg = "Saved."
                onSaved()
            } catch {
                busy = false
                msg = "Could not save. Try again."
            }
        }
    }
}

// MARK: - Locked profile: request a change + my request history

struct ProfileChangeRequestSection: View {
    let onChanged: () -> Void

    @State private var reloadKey: Int = 0
    @State private var showDialog: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            InfoCard {
                Text("🔒 Your profile is locked").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
                Text("Need a correction? Request a change — HR/Admin will review and apply it.")
                    .font(.bodySmall).foregroundColor(.Muted)
                HROutlinedButton("✏ Request a change") { showDialog = true }
                    .padding(.top, 8)
            }
            AsyncContent(key: AnyHashable(reloadKey), load: { () async throws -> [ProfileChangeRequest] in
                try await API.shared.myChangeRequests()
            }) { reqs, _ in
                if !reqs.isEmpty {
                    myRequests(reqs)
                }
            }
        }
        .sheet(isPresented: $showDialog) {
            ProfileChangeRequestSheet(onDismiss: { showDialog = false }, onSubmitted: {
                showDialog = false
                reloadKey += 1
                onChanged()
            })
        }
    }

    private func myRequests(_ reqs: [ProfileChangeRequest]) -> some View {
        InfoCard {
            Text("My change requests").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
                .padding(.bottom, 6)
            ForEach(reqs) { r in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.fieldLabel ?? r.field).font(.bodyMedium.weight(.medium)).foregroundColor(.TextDark)
                        Text(changeLine(r)).font(.bodySmall).foregroundColor(.Muted)
                        if let n = r.reviewNote, !n.isEmpty {
                            Text(n).font(.labelSmall).foregroundColor(.Muted)
                        }
                    }
                    Spacer()
                    Text(r.status.uppercased()).font(.labelSmall.weight(.semibold))
                        .foregroundColor(CRFmt.statusColor(r.status))
                }
                .padding(.vertical, 4)
            }
        }
    }

    private func changeLine(_ r: ProfileChangeRequest) -> String {
        let old: String = r.oldValue ?? ""
        return (old.isEmpty ? "" : "\(old) → ") + (r.newValue ?? "")
    }
}

struct ProfileChangeRequestSheet: View {
    let onDismiss: () -> Void
    let onSubmitted: () -> Void

    @State private var fields: [ChangeField] = []
    @State private var selected: ChangeField? = nil
    @State private var value: String = ""
    @State private var note: String = ""
    @State private var busy: Bool = false
    @State private var err: String? = nil

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Field to change").font(.labelSmall).foregroundColor(.Muted)
                    fieldMenu
                    if let f = selected {
                        Text("Current: \(f.current ?? "—")").font(.labelSmall).foregroundColor(.Muted)
                    }
                    HRField("New value", text: $value)
                    HRField("Reason (optional)", text: $note, multiline: true)
                    if let e = err {
                        Text(e).font(.bodySmall).foregroundColor(.Bad)
                    }
                    HRFilledButton(busy ? "Sending…" : "Submit", enabled: !busy) { submit() }
                        .padding(.top, 6)
                }
                .padding(20)
            }
            .navigationTitle("Request a change")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onDismiss() }.disabled(busy)
                }
            }
        }
        .interactiveDismissDisabled(busy)
        .task {
            fields = (try? await API.shared.myChangeFields()) ?? []
        }
    }

    private var fieldMenu: some View {
        Menu {
            ForEach(fields, id: \.field) { f in
                Button(f.label) {
                    selected = f
                    value = ""
                }
            }
        } label: {
            HStack {
                Text(selected?.label ?? "Choose a field…").foregroundColor(.TextDark).font(.bodyMedium)
                Spacer()
                Image(systemName: "chevron.down").foregroundColor(.Muted)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 20).stroke(Color.BrandBlue.opacity(0.6), lineWidth: 1))
        }
    }

    private func submit() {
        guard let f = selected else {
            err = "Pick a field to change."
            return
        }
        let v: String = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if v.isEmpty {
            err = "Enter the new value."
            return
        }
        err = nil
        busy = true
        let n: String? = note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : note
        Task { @MainActor in
            do {
                _ = try await API.shared.submitChangeRequest(field: f.field, value: v, note: n)
                busy = false
                onSubmitted()
            } catch {
                busy = false
                err = "Could not send. " + (error.localizedDescription.isEmpty ? "Try again." : error.localizedDescription)
            }
        }
    }
}

// MARK: - Change password

struct ProfileChangePasswordSheet: View {
    let onDismiss: () -> Void

    @EnvironmentObject var app: AppState
    @State private var current: String = ""
    @State private var next: String = ""
    @State private var confirm: String = ""
    @State private var busy: Bool = false
    @State private var err: String? = nil
    @State private var done: Bool = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if done {
                        Text("Your password has been updated.").font(.bodyMedium).foregroundColor(.TextDark)
                        HRFilledButton("Done") { onDismiss() }.padding(.top, 6)
                    } else {
                        form
                    }
                }
                .padding(20)
            }
            .navigationTitle(done ? "Password changed" : "Change password")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if !done {
                        Button("Cancel") { onDismiss() }.disabled(busy)
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .interactiveDismissDisabled(busy)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 8) {
            HRField("Current password", text: $current, secure: true)
            HRField("New password", text: $next, secure: true)
            HRField("Confirm new password", text: $confirm, secure: true)
            if let e = err {
                Text(e).font(.bodySmall).foregroundColor(.Bad)
            }
            HRFilledButton(busy ? "Saving…" : "Update", enabled: !busy) { update() }
                .padding(.top, 6)
        }
    }

    private func update() {
        if next.count < 6 {
            err = "New password must be at least 6 characters."
        } else if next != confirm {
            err = "New passwords don't match."
        } else if next == current {
            err = "New password must be different."
        } else {
            err = nil
        }
        if err != nil { return }
        busy = true
        let cur: String = current
        let nw: String = next
        Task { @MainActor in
            do {
                let t: Token = try await API.shared.changePassword(current: cur, new: nw)
                app.passwordChanged(t)
                busy = false
                done = true
            } catch {
                busy = false
                err = "Current password is incorrect."
            }
        }
    }
}
