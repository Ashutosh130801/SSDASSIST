import SwiftUI
import UIKit

// Shared bits for the Detail sheets + iOS extras on the case screen:
//   DetailChipRow           — Kotlin ChipRow (FlowRow of FilterChips)
//   DetailAmountField       — numeric "Amount (₹)" text field (digits + '.')
//   DetailUpiSheet          — UPI QR + pay link for the case's pending amount (company VPA from /api/config)
//   DetailContactUpdateSheet — caller / head office records the customer's latest phone / address

// MARK: - Chip row

struct DetailChipRow: View {
    let options: [String]
    let selected: String
    let onSelect: (String) -> Void

    init(_ options: [String], selected: String, onSelect: @escaping (String) -> Void) {
        self.options = options
        self.selected = selected
        self.onSelect = onSelect
    }

    var body: some View {
        FlowLayout(spacing: 6, lineSpacing: 6) {
            ForEach(options, id: \.self) { opt in
                Chip(label: opt, selected: selected == opt) { onSelect(opt) }
            }
        }
    }
}

/// Small grey caption above a form control (Kotlin labelSmall / MutedDim).
struct DetailCaption: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(.labelSmall).foregroundColor(.MutedDim)
    }
}

/// Numeric amount field that keeps only digits and '.' (Kotlin filter { isDigit() || c == '.' }).
struct DetailAmountField: View {
    let label: String
    @Binding var text: String

    init(label: String, text: Binding<String>) {
        self.label = label
        self._text = text
    }

    var body: some View {
        LabeledField(label: label) {
            TextField("0", text: Binding<String>(
                get: { text },
                set: { (v: String) in text = String(v.filter { $0.isNumber || $0 == "." }) }
            ))
            .keyboardType(.decimalPad)
        }
    }
}

/// Parses "1234.5" → 1234.5, else 0 (Kotlin toDoubleOrNull() ?: 0.0).
func detailAmount(_ s: String) -> Double {
    return Double(s.trimmingCharacters(in: .whitespaces)) ?? 0.0
}

// MARK: - UPI QR / pay link

struct DetailUpiSheet: View {
    let c: Case
    let vpa: String
    let payee: String?
    let onDone: () -> Void

    @State private var amountText: String = ""

    init(c: Case, vpa: String, payee: String?, onDone: @escaping () -> Void) {
        self.c = c
        self.vpa = vpa
        self.payee = payee
        self.onDone = onDone
    }

    private var amount: Double { detailAmount(amountText) }

    private var note: String {
        var s: String = "Case " + String(c.id)
        if let a = CaseText.nb(c.accountNo) ?? CaseText.nb(c.cardNo) { s += " " + a }
        return s
    }

    private var payLabel: String {
        var s: String = "Pay to " + vpa
        if let p = payee, !p.isEmpty { s += " (" + p + ")" }
        return s
    }

    private var link: String {
        return Actions.upiLink(vpa: vpa, payee: payee, amount: amount > 0 ? amount : nil, note: note)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    Text(c.customerName ?? "Customer").font(.titleMedium).foregroundColor(.TextDark)
                    QrImage(content: link, size: 220)
                        .padding(8)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white))
                    Text(payLabel)
                        .font(.bodySmall).foregroundColor(.Muted)
                        .multilineTextAlignment(.center)
                    DetailAmountField(label: "Amount (₹)", text: $amountText)
                    actions
                }
                .padding(16)
            }
            .navigationTitle("UPI payment")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { onDone() } }
            }
        }
        .onAppear {
            let p: Double = CaseText.pending(c)
            if amountText.isEmpty && p > 0 { amountText = String(format: "%.0f", p) }
        }
    }

    private var shareText: String {
        var s: String = "Dear " + (c.customerName ?? "Customer") + ", please pay"
        if amount > 0 { s += " " + inr(amount) }
        s += " via UPI to " + vpa + ".\n" + link
        return s
    }

    private var actions: some View {
        VStack(spacing: 8) {
            Button(action: { Actions.whatsApp(c.phone, text: shareText) }) {
                Label("Send pay link on WhatsApp", systemImage: "message.fill").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.borderedProminent).tint(.Good)
            Button(action: { shareQr() }) {
                Label("Share QR / link", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
            Button(action: { Actions.openUpi(vpa: vpa, payee: payee, amount: amount > 0 ? amount : nil, note: note) }) {
                Label("Open UPI app", systemImage: "indianrupeesign.circle").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
            Button(action: {
                UIPasteboard.general.string = link
                showToast("UPI link copied")
            }) {
                Label("Copy link", systemImage: "doc.on.doc").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
        }
    }

    private func shareQr() {
        var items: [Any] = [shareText]
        if let img = Qr.image(link, size: 768) { items.append(img) }
        Actions.share(items: items)
    }
}

// MARK: - Contact update

struct DetailContactUpdateSheet: View {
    let c: Case
    let onDone: () -> Void

    @State private var phone: String = ""
    @State private var address: String = ""
    @State private var busy: Bool = false
    @State private var error: String? = nil
    @State private var seeded: Bool = false

    init(c: Case, onDone: @escaping () -> Void) {
        self.c = c
        self.onDone = onDone
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Record the customer's latest phone / address. The field agent is notified.")
                        .font(.bodySmall).foregroundColor(.Muted)
                    if let e = error {
                        Text(e).font(.labelMedium).foregroundColor(.Bad)
                    }
                    LabeledField(label: "New phone") {
                        TextField("Phone", text: $phone).keyboardType(.phonePad)
                    }
                    LabeledField(label: "New address") {
                        TextField("Address", text: $address, axis: .vertical).lineLimit(2...5)
                    }
                    PrimaryButton(title: "Save", busy: busy, enabled: canSave) { save() }
                }
                .padding(16)
            }
            .navigationTitle("Update contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { onDone() }.disabled(busy) }
            }
        }
        .interactiveDismissDisabled(busy)
        .onAppear {
            if !seeded {
                seeded = true
                phone = c.newPhone ?? ""
                address = c.newAddress ?? ""
            }
        }
    }

    private var canSave: Bool {
        return CaseText.nb(phone) != nil || CaseText.nb(address) != nil
    }

    private func save() {
        busy = true
        error = nil
        let p: String? = CaseText.nb(phone)
        let a: String? = CaseText.nb(address)
        Task {
            do {
                _ = try await API.shared.contactUpdate(caseId: c.id, newAddress: a, newPhone: p)
                busy = false
                showToast("Contact updated — FOS notified")
                onDone()
            } catch {
                busy = false
                self.error = error.localizedDescription
            }
        }
    }
}
