import SwiftUI

/// "Record payment" — port of PaymentDialog in ui/detail/Dialogs.kt.
/// Amount (prefilled with the case's pending amount), mode chips, and STAB / NORM for credit cards.
/// Posts `API.recordPayment(id:amount:mode:normStab:)`; closes via `onDone` only after the server confirms.
struct PaymentSheet: View {
    let `case`: Case
    let onDone: () -> Void

    @State private var amount: String = ""
    @State private var mode: String = "UPI"
    @State private var normStab: String = "STAB"
    @State private var busy: Bool = false
    @State private var error: String? = nil
    @State private var seeded: Bool = false

    private static let modes: [String] = ["UPI", "Cash", "Bank", "Card", "Cheque"]

    init(case c: Case, onDone: @escaping () -> Void) {
        self.case = c
        self.onDone = onDone
    }

    private var isCreditCard: Bool { self.case.segment == "Credit Card" }
    private var amt: Double { detailAmount(amount) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header
                    if let e = error {
                        Text(e).font(.labelMedium).foregroundColor(.Bad)
                    }
                    DetailAmountField(label: "Amount (₹)", text: $amount)
                    DetailCaption("Mode")
                    DetailChipRow(PaymentSheet.modes, selected: mode) { mode = $0 }
                    if isCreditCard {
                        DetailCaption("Paid at (credit card)")
                        DetailChipRow(["STAB", "NORM"], selected: normStab) { normStab = $0 }
                    }
                    PrimaryButton(title: "Save", busy: busy, enabled: amt > 0) { save() }
                        .padding(.top, 6)
                }
                .padding(16)
            }
            .navigationTitle("Record payment")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onDone() }.disabled(busy)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.disabled(busy || amt <= 0)
                }
            }
        }
        .interactiveDismissDisabled(busy)
        .onAppear {
            if !seeded {
                seeded = true
                let m: Double = self.case.pendingAmount
                amount = m > 0 ? String(format: "%.0f", m) : ""
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(self.case.customerName ?? "Case #" + String(self.case.id))
                .font(.titleMedium).foregroundColor(.TextDark)
            Text("Pending " + inr(self.case.pendingAmount) + " · Received " + inr(self.case.receivedAmount))
                .font(.bodySmall).foregroundColor(.Muted)
        }
    }

    private func save() {
        let a: Double = amt
        guard a > 0, !busy else { return }
        busy = true
        error = nil
        let ns: String? = isCreditCard ? normStab : nil
        let id: Int = self.case.id
        let m: String = mode
        Task {
            do {
                _ = try await API.shared.recordPayment(id: id, amount: a, mode: m, normStab: ns)
                busy = false
                showToast("Payment recorded")
                onDone()
            } catch {
                busy = false
                self.error = error.localizedDescription
            }
        }
    }
}
