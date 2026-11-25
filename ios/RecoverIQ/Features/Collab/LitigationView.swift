import SwiftUI

// Port of ui/screens/LitigationScreen.kt — legal insights strip, matters list (delete), "New matter" dialog.

struct LitigationView: View {
    init() {}

    @State private var refresh: Int = 0
    @State private var showAdd: Bool = false

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            VStack(spacing: 0) {
                AsyncContent(key: AnyHashable("ins\(refresh)"), load: { try await API.shared.legalInsights() }) { (ins: LegalInsights, _: @escaping () -> Void) in
                    HStack(spacing: 8) {
                        LegalStat(label: "Open", value: ins.open, color: .BrandBlue)
                        LegalStat(label: "Overdue", value: ins.hearingOverdue, color: .Bad)
                        LegalStat(label: "Today", value: ins.hearingToday, color: .Warn)
                        LegalStat(label: "This wk", value: ins.hearingWeek, color: .Muted)
                    }
                    .padding(.top, 12)
                }
                .frame(maxHeight: 110)
                AsyncContent(key: AnyHashable(refresh), load: { try await API.shared.legalCases() }) { (cases: [Legal], _: @escaping () -> Void) in
                    if cases.isEmpty {
                        EmptyState("No litigation matters yet.")
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 10) {
                                ForEach(cases) { l in
                                    LegalCard(l: l, onDelete: { delete(l.id) })
                                }
                            }
                            .padding(.top, 10)
                            .padding(.bottom, 90)
                        }
                    }
                }
            }
            .padding(.horizontal, 12)
            CollabExtendedFab("New matter") { showAdd = true }
        }
        .sheet(isPresented: $showAdd) {
            AddLegalSheet(onDismiss: { showAdd = false }, onConfirm: { body in create(body) })
        }
    }

    private func delete(_ id: Int) {
        Task {
            try? await API.shared.deleteLegal(id: id)
            refresh += 1
        }
    }

    private func create(_ body: LegalCreate) {
        Task {
            _ = try? await API.shared.createLegal(body: body)
            showAdd = false
            refresh += 1
        }
    }
}

private struct LegalStat: View {
    let label: String
    let value: Int
    let color: Color

    var body: some View {
        InfoCard(spacing: 2, padding: 12) {
            Text(String(value)).font(.titleLarge).fontWeight(.bold).foregroundColor(color)
            Text(label).font(.labelSmall).foregroundColor(.Muted).lineLimit(1)
        }
    }
}

private struct LegalCard: View {
    let l: Legal
    let onDelete: () -> Void

    private var meta: String {
        let parts: [String?] = [l.matterType, l.court, l.caseNumber]
        return parts.compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        InfoCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(l.borrowerName ?? l.matterType ?? "Legal matter").fontWeight(.semibold).foregroundColor(.TextDark)
                    Text(meta).font(.bodySmall).foregroundColor(.Muted)
                    if let h = l.nextHearingDate {
                        Text("Next hearing: \(DateUtil.humanDate(h))").font(.bodySmall).foregroundColor(.Warn)
                    }
                    if l.amount > 0 {
                        Text(inr(l.amount)).font(.labelMedium).foregroundColor(.BrandBlue)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 6) {
                    StatusChip(l.status)
                    Button(action: onDelete) {
                        Image(systemName: "trash.fill").foregroundColor(.Bad).frame(width: 36, height: 36)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Delete")
                }
            }
        }
    }
}

private struct AddLegalSheet: View {
    let onDismiss: () -> Void
    let onConfirm: (LegalCreate) -> Void

    @State private var borrower: String = ""
    @State private var matter: String = ""
    @State private var court: String = ""
    @State private var caseNo: String = ""
    @State private var amount: String = ""

    private func blankToNil(_ s: String) -> String? {
        s.trimmingCharacters(in: .whitespaces).isEmpty ? nil : s
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 8) {
                    CollabField("Borrower name", text: $borrower)
                    CollabField("Matter type (e.g. Sec 138, Arbitration)", text: $matter)
                    CollabField("Court", text: $court)
                    CollabField("Case number", text: $caseNo)
                    CollabField("Amount (₹)", text: $amount, keyboard: .decimalPad)
                        .onChange(of: amount) { v in
                            let f: String = v.filter { $0.isNumber || $0 == "." }
                            if f != v { amount = f }
                        }
                }
                .padding(16)
            }
            .navigationTitle("New litigation matter")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onDismiss) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        onConfirm(LegalCreate(matterType: matter,
                                              borrowerName: blankToNil(borrower),
                                              court: blankToNil(court),
                                              caseNumber: blankToNil(caseNo),
                                              amount: Double(amount) ?? 0.0))
                    }
                    .disabled(matter.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
