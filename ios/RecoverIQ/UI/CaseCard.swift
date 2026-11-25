import SwiftUI

/// Port of ui/common/CaseCard.kt. Tinted by work state (fresh / touched today / paid), red border when
/// escalated or flagged, optional quick Call / WhatsApp buttons and tappable FOS/caller chips.
///
/// `CaseCard(case: c, onClick: { onOpenCase(c.id) })`
/// `CaseCard(case: c, onClick: {…}, showQuickActions: false, onOpenPerf: { id, role in … })`
struct CaseCard: View {
    let `case`: Case
    let onClick: () -> Void
    var showQuickActions: Bool = true
    var subtitle: String? = nil
    var onOpenPerf: ((Int, String) -> Void)? = nil

    init(case c: Case, onClick: @escaping () -> Void, showQuickActions: Bool = true,
         subtitle: String? = nil, onOpenPerf: ((Int, String) -> Void)? = nil) {
        self.case = c
        self.onClick = onClick
        self.showQuickActions = showQuickActions
        self.subtitle = subtitle
        self.onOpenPerf = onOpenPerf
    }

    private var state: String { self.case.workState }

    private var cardColor: Color {
        switch state {
        case "paid": return Color.Good.opacity(0.10)
        case "touched": return Color.Warn.opacity(0.12)
        default: return Color.CardWhite
        }
    }

    private var cardBorder: Color {
        let c = self.case
        if c.escalated == true { return Color.Bad.opacity(0.8) }
        if c.flagged == true { return Color.Bad.opacity(0.7) }
        if state == "paid" { return Color.Good.opacity(0.5) }
        if state == "touched" { return Color.Warn.opacity(0.5) }
        return Color.GlassStroke
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 8) {
                leftColumn
                Spacer(minLength: 4)
                amountColumn
            }
            if showPersonRow { personRow.padding(.top, 6) }
            bottomRow.padding(.top, 8)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.CardWhite))
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(cardColor))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(cardBorder, lineWidth: 1))
        .shadow(color: Color.black.opacity(0.05), radius: 5, x: 0, y: 2)
        .contentShape(Rectangle())
        .onTapGesture { onClick() }
    }

    // MARK: pieces

    private var titleText: String {
        let c = self.case
        return (c.flagged == true ? "⚠️ " : "") + (c.customerName ?? "Unnamed customer")
    }

    private var line2: String {
        let c = self.case
        return [c.accountNo, c.bank, c.product].compactMap { $0 }.joined(separator: " · ")
    }

    private var meta: String {
        let c = self.case
        let parts: [String?] = [c.bucket.map { "Bkt " + $0 }, c.cycle.map { "cyc " + $0 }, c.team, c.pincode]
        return parts.compactMap { $0 }.joined(separator: " · ")
    }

    private var snippet: String? {
        let c = self.case
        guard let s = c.disposition ?? c.remarks, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return "• " + String(s.prefix(48))
    }

    private var leftColumn: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                if let rc = reviewColorOf(self.case.reviewColor) {
                    Circle().fill(rc).frame(width: 11, height: 11)
                }
                Text(titleText).font(.system(size: 14, weight: .bold)).foregroundColor(.TextDark).lineLimit(2)
            }
            if !line2.isEmpty { Text(line2).font(.bodySmall).foregroundColor(.Muted).lineLimit(2) }
            if !meta.isEmpty { Text(meta).font(.labelSmall).foregroundColor(.Muted).lineLimit(1) }
            if let s = snippet { Text(s).font(.labelSmall).foregroundColor(.MutedDim).lineLimit(1) }
            if let sub = subtitle, !sub.isEmpty { Text(sub).font(.labelSmall).foregroundColor(.Muted).lineLimit(2) }
        }
    }

    private var amountColumn: some View {
        let c = self.case
        let base: Double = c.enr > 0 ? c.enr : c.totalOutstanding
        let showNS: Bool = c.isSettlementCase && (c.paidStatus ?? "").uppercased() != "PAID"
        return VStack(alignment: .trailing, spacing: 1) {
            Text(inr(c.pendingAmount)).font(.system(size: 15, weight: .bold)).foregroundColor(.BrandBlue)
            Text("of " + inr(base)).font(.labelSmall).foregroundColor(.MutedDim)
            if c.receivedAmount > 0 {
                Text("paid " + inr(c.receivedAmount)).font(.labelSmall).foregroundColor(.Good)
            }
            if showNS, let n = c.remainingToNorm {
                Text("N: " + inr(n)).font(.labelSmall).foregroundColor(.Muted)
            }
            if showNS, let s = c.remainingToStab {
                Text("S: " + inr(s)).font(.labelSmall).foregroundColor(.Muted)
            }
        }
    }

    private var showPersonRow: Bool {
        onOpenPerf != nil && (self.case.assignedCallerId != nil || self.case.assignedFosId != nil)
    }

    private var personRow: some View {
        let c = self.case
        return HStack(spacing: 6) {
            if let id = c.assignedCallerId {
                PersonChip(text: "📞 " + (c.assignedCallerName ?? c.callerName ?? "Caller")) { onOpenPerf?(id, "caller") }
            }
            if let id = c.assignedFosId {
                PersonChip(text: "🧍 " + (c.assignedFosName ?? c.fosName ?? "FOS")) { onOpenPerf?(id, "fos") }
            }
        }
    }

    private var bottomRow: some View {
        let c = self.case
        let hasPhone: Bool = !(c.phone ?? "").trimmingCharacters(in: .whitespaces).isEmpty
        return HStack(alignment: .center, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    StatusChip(status: c.status)
                    PaidTag(paidStatus: c.paidStatus)
                    if state == "paid" {
                        TouchTag(text: "PAID", color: .Good)
                    } else if state == "touched" {
                        TouchTag(text: c.visitedToday == true ? "VISITED" : "DONE TODAY", color: .Warn)
                    }
                    if c.escalated == true { TouchTag(text: "🚩 ESCALATED · LOCKED", color: .Bad) }
                    if c.flagged == true { TouchTag(text: "⚠ REVIEW", color: .Bad) }
                }
            }
            if showQuickActions && hasPhone {
                Button(action: { Actions.call(c.phone) }) {
                    Image(systemName: "phone.fill").foregroundColor(.BrandBlue).frame(width: 34, height: 34)
                }
                .buttonStyle(.plain)
                Button(action: { Actions.whatsApp(c.phone) }) {
                    Image(systemName: "message.fill").foregroundColor(.Good).frame(width: 34, height: 34)
                }
                .buttonStyle(.plain)
            }
        }
    }
}
