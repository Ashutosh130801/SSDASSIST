import SwiftUI

// Port of ui/fos/JointCasesScreen.kt — cases another FOS owns, sent to me for a new-address visit.
// I visit and collect; the case counts for me only once I log a paid visit (then it drops off this list).

struct JointCasesView: View {
    var onOpenCase: (Int) -> Void

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    @State private var rows: [Case]? = nil
    @State private var loading: Bool = true
    @State private var error: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Joint Cases")
            Text("Cases another FOS owns, sent to you to visit a new address and collect. They count for you only after you log a paid visit.")
                .font(.system(size: 12)).foregroundColor(.MutedDim)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 10)
            stateContent
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task { await load() }
    }

    @ViewBuilder private var stateContent: some View {
        if loading {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let e = error {
            Text(e).foregroundColor(.Bad).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if (rows ?? []).isEmpty {
            Text("No joint cases right now.").foregroundColor(.MutedDim)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(rows ?? []) { c in
                        JointCaseRow(c: c, onOpenCase: onOpenCase)
                    }
                }
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        do {
            let v: [Case] = try await API.shared.jointCases()
            rows = v
        } catch {
            if error is CancellationError { return }
            let msg: String = error.localizedDescription
            self.error = msg.isEmpty ? "Could not load joint cases" : msg
        }
        loading = false
    }
}

private struct JointCaseRow: View {
    let c: Case
    let onOpenCase: (Int) -> Void

    var body: some View {
        Button(action: { onOpenCase(c.id) }) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline) {
                    Text(c.customerName ?? "—")
                        .font(.system(size: 15, weight: .bold)).foregroundColor(.TextDark)
                    Spacer()
                    Text(inr(c.pendingAmount)).fontWeight(.bold).foregroundColor(.Bad)
                }
                Text("\(c.bank ?? "—") · \(c.product ?? "—")")
                    .font(.system(size: 12)).foregroundColor(.Muted)
                if let f = c.fosName {
                    Text("Primary FOS: \(f)").font(.system(size: 12)).foregroundColor(.MutedDim)
                }
                if let n = c.jointNote, !n.trimmingCharacters(in: .whitespaces).isEmpty {
                    Text("📍 \(n)").font(.system(size: 12)).foregroundColor(.BrandBlue)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite))
            .shadow(color: Color.black.opacity(0.06), radius: 2, x: 0, y: 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
