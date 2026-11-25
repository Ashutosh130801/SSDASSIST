import SwiftUI

/// "Log call outcome" — port of LogCallDialog in ui/detail/Dialogs.kt.
/// Field officers (phonePtpOnly) can't book a payment from a phone call — PAID is removed for them;
/// they can still record a phone PTP. Posts `API.logCall(body: CallCreate)`.
struct LogCallSheet: View {
    let `case`: Case
    let onDone: () -> Void

    @EnvironmentObject var app: AppState

    @State private var disp: String = "PTP"
    @State private var amount: String = ""
    @State private var note: String = ""
    @State private var normStab: String = "STAB"
    @State private var dateIso: String = DateUtil.plusDaysIso(1)
    @State private var busy: Bool = false
    @State private var error: String? = nil

    init(case c: Case, onDone: @escaping () -> Void) {
        self.case = c
        self.onDone = onDone
    }

    private var phonePtpOnly: Bool { app.user?.isFieldAgent ?? false }
    private var isCreditCard: Bool { self.case.segment == "Credit Card" }

    private var dispositions: [String] {
        if phonePtpOnly {
            return ["PTP", "RTP", "CALLBACK", "NO_CONTACT", "WRONG_NUMBER", "REFUSED"]
        }
        return ["PTP", "RTP", "PAID", "CALLBACK", "NO_CONTACT", "WRONG_NUMBER", "REFUSED"]
    }

    private var showAmount: Bool {
        return disp == "PTP" || disp == "RTP" || (disp == "PAID" && !phonePtpOnly)
    }

    private var showDate: Bool {
        return disp == "PTP" || disp == "RTP" || disp == "CALLBACK"
    }

    private var amt: Double { detailAmount(amount) }

    var body: some View {
        NavigationStack {
            ScrollView {
                form.padding(16)
            }
            .navigationTitle(phonePtpOnly ? "Log phone outcome" : "Log call outcome")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onDone() }.disabled(busy)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.disabled(busy)
                }
            }
        }
        .interactiveDismissDisabled(busy)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(self.case.customerName ?? "Case #" + String(self.case.id))
                .font(.titleMedium).foregroundColor(.TextDark)
            if phonePtpOnly {
                DetailCaption("Phone call before visit — record a promise-to-pay. Collections are booked from a field visit.")
            }
            if let e = error {
                Text(e).font(.labelMedium).foregroundColor(.Bad)
            }
            DetailCaption("Disposition")
            DetailChipRow(dispositions, selected: disp) { disp = $0 }
            if showAmount {
                DetailAmountField(label: disp == "PAID" ? "Amount collected (₹)" : "Promised amount (₹)", text: $amount)
            }
            if disp == "PAID" && isCreditCard {
                DetailCaption("Paid at (credit card)")
                DetailChipRow(["STAB", "NORM"], selected: normStab) { normStab = $0 }
            }
            if showDate {
                DetailCaption(disp == "CALLBACK" ? "Call back on" : "Promised date")
                DatePickerField(label: "Pick date", iso: dateIso) { dateIso = $0 }
            }
            LabeledField(label: "Note (optional)") {
                TextField("Note", text: $note, axis: .vertical).lineLimit(1...4)
            }
            PrimaryButton(title: "Save", busy: busy) { save() }
                .padding(.top, 6)
        }
    }

    private func buildCall() -> CallCreate {
        let isPromise: Bool = disp == "PTP" || disp == "RTP"
        let n: String = note.trimmingCharacters(in: .whitespacesAndNewlines)
        return CallCreate(
            caseId: self.case.id,
            disposition: disp,
            ptpAmount: isPromise ? amt : 0.0,
            ptpDate: isPromise ? dateIso : nil,
            followUpDate: disp == "CALLBACK" ? dateIso : nil,
            paidAmount: disp == "PAID" ? amt : 0.0,
            normStab: (disp == "PAID" && isCreditCard) ? normStab : nil,
            note: n.isEmpty ? nil : note
        )
    }

    private func save() {
        guard !busy else { return }
        let call: CallCreate = buildCall()
        busy = true
        error = nil
        Task {
            do {
                _ = try await API.shared.logCall(body: call)
                busy = false
                showToast("Call logged")
                onDone()
            } catch {
                busy = false
                self.error = error.localizedDescription
            }
        }
    }
}
