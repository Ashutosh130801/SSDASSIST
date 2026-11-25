import SwiftUI

/// Port of ui/common/PortfolioScreen.kt — bank-first portfolio browsing: banks → products of a bank →
/// (location cards only when a product was uploaded with an explicit branch) → the filtered case list.
/// FOS/caller names on every case are tappable and open that person's performance sheet.
struct PortfolioView: View {
    var onOpenCase: (Int) -> Void

    @State private var bankSel: String? = nil
    @State private var productSel: ProductSummary? = nil
    @State private var branchSel: String? = nil
    @State private var perfTarget: ClrPerfTarget? = nil
    // Persistent, top-of-section month filter — each month is a separate book (nothing merged).
    @State private var monthB: String = "current"

    private let months: [ClrMonthOption] = [
        ClrMonthOption(value: "current", label: "This month"),
        ClrMonthOption(value: "next", label: "Next"),
        ClrMonthOption(value: "", label: "All"),
    ]

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    private var showCases: Bool {
        guard let p = productSel else { return false }
        return !p.branchSplit || branchSel != nil
    }

    private var title: String {
        if showCases, let p = productSel {
            var parts: [String] = [p.bank, p.product]
            if let b = branchSel, !b.trimmingCharacters(in: .whitespaces).isEmpty { parts.append(b) }
            return parts.joined(separator: " · ")
        }
        if let p = productSel { return "\(p.bank) · \(p.product) · locations" }
        if let b = bankSel { return b }
        return "Portfolios"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ClrMonthChips(options: months, selected: $monthB, leading: "Month:")
                .padding(.top, 8)
            headerRow.padding(.vertical, 8)
            content
        }
        .padding(.horizontal, 12)
        .sheet(item: $perfTarget) { t in
            ClrPerformanceSheet(empId: t.empId, role: t.role, onDismiss: { perfTarget = nil })
        }
    }

    private var headerRow: some View {
        HStack(spacing: 2) {
            if bankSel != nil {
                Button(action: goBack) {
                    Text("← Back").foregroundColor(.BrandBlue)
                }
                .padding(.trailing, 6)
            }
            SectionTitle(title).padding(.leading, 2)
        }
    }

    private func goBack() {
        if showCases, let p = productSel, p.branchSplit {
            branchSel = nil                       // cases → back to locations
        } else if productSel != nil {
            productSel = nil                      // → back to products
            branchSel = nil
        } else {
            bankSel = nil                         // → back to banks
        }
    }

    @ViewBuilder private var content: some View {
        if showCases, let p = productSel {
            PortfolioCasesList(p: p, branch: branchSel, onOpenCase: onOpenCase) { id, role in
                perfTarget = ClrPerfTarget(empId: id, role: role)
            }
        } else if let p = productSel {
            PortfolioBranchCards(product: p) { br in branchSel = br }
        } else if let b = bankSel {
            PortfolioProductCards(bank: b, monthB: monthB) { p in
                productSel = p
                branchSel = (p.branchSplit && !p.branches.isEmpty) ? nil : ""
            }
        } else {
            PortfolioBankCards(monthB: monthB) { b in bankSel = b }
        }
    }
}

// MARK: - Cards

private struct PfBankLogo: View {
    let bank: String
    let domain: String?
    var size: CGFloat = 44

    private var initials: String {
        let letters = String(bank.filter { $0.isLetter }.prefix(2)).uppercased()
        return letters.isEmpty ? "#" : letters
    }

    private var box: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 11).fill(Color.BrandBlue)
            Text(initials).fontWeight(.bold).foregroundColor(.white)
        }
        .frame(width: size, height: size)
    }

    var body: some View {
        if let d = domain, !d.trimmingCharacters(in: .whitespaces).isEmpty,
           let url = URL(string: "https://www.google.com/s2/favicons?sz=128&domain=\(d)") {
            // Clearbit's free logo API was retired; Google's favicon service is reliable.
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let img):
                    img.resizable().scaledToFit()
                        .frame(width: size, height: size)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 11))
                default:
                    box
                }
            }
            .frame(width: size, height: size)
        } else {
            box
        }
    }
}

private struct PfMoneyRow: View {
    let received: Double
    let pending: Double

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("Recovered").font(.labelSmall).foregroundColor(.Muted)
                Text(inr(received)).fontWeight(.bold).foregroundColor(.Good)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 1) {
                Text("Pending").font(.labelSmall).foregroundColor(.Muted)
                Text(inr(pending)).fontWeight(.bold).foregroundColor(.Warn)
            }
        }
        .padding(.top, 10)
    }
}

/// Per-portfolio settlement split shown on product & location cards (web "✓ N paid · N unpaid").
private struct PfPaidUnpaidLine: View {
    let paid: Int
    let unpaid: Int

    var body: some View {
        if paid != 0 || unpaid != 0 {
            Text("✓ \(paid) paid · \(unpaid) unpaid")
                .font(.labelSmall).foregroundColor(.Good).padding(.top, 4)
        }
    }
}

private struct PfCard<Content: View>: View {
    let onClick: () -> Void
    let content: Content

    init(onClick: @escaping () -> Void, @ViewBuilder content: () -> Content) {
        self.onClick = onClick
        self.content = content()
    }

    var body: some View {
        Button(action: onClick) {
            VStack(alignment: .leading, spacing: 2) { content }
                .foregroundColor(.TextDark)
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.GlassStroke, lineWidth: 1))
                .shadow(color: Color.black.opacity(0.07), radius: 6, x: 0, y: 3)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private struct PortfolioBankCards: View {
    let monthB: String
    let onPick: (String) -> Void

    var body: some View {
        AsyncContent(key: AnyHashable("banks|\(monthB)"),
                     load: { try await API.shared.portfolioBanks(monthBucket: monthB) }) { banks, _ in
            if banks.isEmpty {
                EmptyState(text: "No cases uploaded yet.")
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(0..<banks.count, id: \.self) { i in
                            bankCard(banks[i])
                        }
                    }
                    .padding(.bottom, 16)
                }
            }
        }
    }

    private func bankCard(_ b: PortfolioBank) -> some View {
        PfCard(onClick: { onPick(b.bank) }) {
            HStack(spacing: 12) {
                PfBankLogo(bank: b.bank, domain: b.logoDomain)
                VStack(alignment: .leading, spacing: 2) {
                    Text(b.bank).font(.titleMedium).fontWeight(.bold)
                    Text("\(b.productCount) product\(b.productCount == 1 ? "" : "s") · \(b.count) cases")
                        .font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer(minLength: 0)
            }
            PfMoneyRow(received: b.received, pending: b.pending)
        }
    }
}

private struct PortfolioProductCards: View {
    let bank: String
    let monthB: String
    let onPick: (ProductSummary) -> Void

    var body: some View {
        AsyncContent(key: AnyHashable("prod|\(bank)|\(monthB)"),
                     load: { try await API.shared.productSummary(monthBucket: monthB).filter { $0.bank == bank } }) { prods, _ in
            if prods.isEmpty {
                EmptyState(text: "No products for this bank.")
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(0..<prods.count, id: \.self) { i in
                            productCard(prods[i])
                        }
                    }
                    .padding(.bottom, 16)
                }
            }
        }
    }

    private func subLine(_ p: ProductSummary) -> String {
        var parts: [String] = []
        if let s = p.segment { parts.append(s) }
        if p.branchSplit { parts.append("📍 \(p.branches.count) locations") }
        return parts.joined(separator: " · ")
    }

    private func productCard(_ p: ProductSummary) -> some View {
        let sub: String = subLine(p)
        return PfCard(onClick: { onPick(p) }) {
            HStack {
                Text(p.product).font(.titleSmall).fontWeight(.bold)
                Spacer()
                Text("\(p.count)").foregroundColor(.Muted)
            }
            if !sub.trimmingCharacters(in: .whitespaces).isEmpty {
                Text(sub).font(.labelSmall).foregroundColor(.Muted)
            }
            PfMoneyRow(received: p.received, pending: p.pending)
            PfPaidUnpaidLine(paid: p.paid, unpaid: p.unpaid)
            if p.branchSplit {
                Text("Tap to choose a location →").font(.labelSmall).foregroundColor(.Muted).padding(.top, 6)
            }
        }
    }
}

private struct PortfolioBranchCards: View {
    let product: ProductSummary
    let onPick: (String) -> Void

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ForEach(0..<product.branches.count, id: \.self) { i in
                    branchCard(product.branches[i])
                }
            }
            .padding(.bottom, 16)
        }
    }

    private func branchCard(_ br: BranchBucket) -> some View {
        PfCard(onClick: { onPick(br.branch) }) {
            HStack {
                Text("📍 \(br.branch)").font(.titleSmall).fontWeight(.bold)
                Spacer()
                Text("\(br.count)").foregroundColor(.Muted)
            }
            Text(product.product).font(.labelSmall).foregroundColor(.Muted)
            PfMoneyRow(received: br.received, pending: br.pending)
            PfPaidUnpaidLine(paid: br.paid, unpaid: br.unpaid)
        }
    }
}
