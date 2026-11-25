import SwiftUI

// Sub-views of CaseDetailView (port of CaseHeader / ActionBar / DetailFields / AddressBlock /
// Field / TimelineRow in ui/detail/CaseDetailScreen.kt).

// MARK: - Header

struct DetailHeaderCard: View {
    let c: Case

    var body: some View {
        InfoCard(spacing: 0) {
            HStack(spacing: 12) {
                ZStack {
                    Circle().fill(Color.BrandBlue.opacity(0.12))
                    Text(initial).font(.system(size: 18, weight: .bold)).foregroundColor(.BrandBlue)
                }
                .frame(width: 46, height: 46)
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.customerName ?? "Unnamed customer")
                        .font(.system(size: 16, weight: .bold)).foregroundColor(.TextDark)
                    Text(subtitle).font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer(minLength: 4)
                StatusChip(status: c.status)
            }
            Spacer().frame(height: 12)
            HStack {
                DetailAmount(label: "Pending", value: CaseText.pending(c), color: .BrandBlue)
                Spacer()
                DetailAmount(label: "Received", value: c.receivedAmount, color: .Good)
                Spacer()
                DetailAmount(label: c.fundingAmount > 0 ? "Funded" : "Outstanding",
                             value: CaseText.payBase(c), color: .Muted)
            }
            if let p = c.propensity {
                Spacer().frame(height: 8)
                Text("Recovery propensity: " + String(p) + "%")
                    .font(.labelMedium)
                    .foregroundColor(p >= 60 ? .Good : .Muted)
            }
        }
    }

    private var initial: String {
        let n: String = c.customerName ?? "?"
        return String(n.prefix(1)).uppercased()
    }

    private var subtitle: String {
        return [c.bank, c.product, c.bucket].compactMap { $0 }.joined(separator: " · ")
    }
}

private struct DetailAmount: View {
    let label: String
    let value: Double
    let color: Color

    var body: some View {
        VStack(spacing: 2) {
            Text(inr(value)).font(.system(size: 15, weight: .bold)).foregroundColor(color)
            Text(label).font(.labelSmall).foregroundColor(.MutedDim)
        }
    }
}

// MARK: - Action bar

struct DetailActionBar: View {
    let c: Case
    let meId: Int
    let canPay: Bool
    let canLogCall: Bool
    let canLogVisit: Bool
    let canRequestCallback: Bool
    let canUpdateContact: Bool
    let hasUpi: Bool
    let onPay: () -> Void
    let onLogCall: () -> Void
    let onLogVisit: () -> Void
    let onUpi: () -> Void
    let onContactUpdate: () -> Void

    @State private var showCallChoice: Bool = false
    @State private var cbSent: Bool = false

    init(c: Case, meId: Int, canPay: Bool, canLogCall: Bool, canLogVisit: Bool,
         canRequestCallback: Bool, canUpdateContact: Bool, hasUpi: Bool,
         onPay: @escaping () -> Void, onLogCall: @escaping () -> Void, onLogVisit: @escaping () -> Void,
         onUpi: @escaping () -> Void, onContactUpdate: @escaping () -> Void) {
        self.c = c
        self.meId = meId
        self.canPay = canPay
        self.canLogCall = canLogCall
        self.canLogVisit = canLogVisit
        self.canRequestCallback = canRequestCallback
        self.canUpdateContact = canUpdateContact
        self.hasUpi = hasUpi
        self.onPay = onPay
        self.onLogCall = onLogCall
        self.onLogVisit = onLogVisit
        self.onUpi = onUpi
        self.onContactUpdate = onContactUpdate
    }

    var body: some View {
        VStack(spacing: 8) {
            contactRow
            teamRow
            if canRequestCallback && c.assignedCallerId != nil {
                callbackButton
            }
            mainRow
            extrasRow
        }
        .confirmationDialog("Place the call", isPresented: $showCallChoice, titleVisibility: .visible) {
            Button("Call via Zoiper") { Actions.dialViaZoiper(c.phone) }
            Button("Phone dialer") { Actions.dial(c.phone) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Call " + (c.customerName ?? "this customer") + " through Zoiper (recommended) or your phone dialer?")
        }
    }

    private var contactRow: some View {
        HStack(spacing: 8) {
            DetailIconButton(label: "Call", systemImage: "phone.fill") { showCallChoice = true }
            DetailIconButton(label: "WhatsApp", systemImage: "message.fill") { Actions.whatsApp(c.phone) }
            DetailIconButton(label: "Navigate", systemImage: "location.north.line.fill") { navigate() }
        }
    }

    private var showFos: Bool {
        return CaseText.nb(c.assignedFosPhone) != nil && c.assignedFosId != meId
    }

    private var showCaller: Bool {
        return CaseText.nb(c.assignedCallerPhone) != nil && c.assignedCallerId != meId
    }

    @ViewBuilder private var teamRow: some View {
        if showFos || showCaller {
            HStack(spacing: 8) {
                if showFos {
                    DetailIconButton(label: "Call FOS", systemImage: "phone.fill") { Actions.dial(c.assignedFosPhone) }
                }
                if showCaller {
                    DetailIconButton(label: "Call caller", systemImage: "phone.fill") { Actions.dial(c.assignedCallerPhone) }
                }
            }
        }
    }

    private var callbackButton: some View {
        Button(action: {
            cbSent = true
            Task { _ = try? await API.shared.chatCallback(caseId: c.id, note: nil) }
        }) {
            Text(cbSent ? "✓ Callback requested" : "📞 Request callback")
                .font(.system(size: 14, weight: .medium))
                .frame(maxWidth: .infinity, minHeight: 40)
        }
        .buttonStyle(.bordered)
        .tint(.BrandBlue)
        .disabled(cbSent)
    }

    @ViewBuilder private var mainRow: some View {
        if canPay || canLogCall || canLogVisit {
            HStack(spacing: 8) {
                if canPay {
                    Button(action: onPay) {
                        Label("Payment", systemImage: "indianrupeesign.circle.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .frame(maxWidth: .infinity, minHeight: 40)
                    }
                    .buttonStyle(.borderedProminent).tint(.BrandBlue)
                }
                if canLogCall {
                    Button(action: onLogCall) {
                        Text("Log call").font(.system(size: 14, weight: .semibold))
                            .frame(maxWidth: .infinity, minHeight: 40)
                    }
                    .buttonStyle(.bordered).tint(.BrandBlue)
                }
                if canLogVisit {
                    Button(action: onLogVisit) {
                        Label("Visit", systemImage: "camera.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .frame(maxWidth: .infinity, minHeight: 40)
                    }
                    .buttonStyle(.borderedProminent).tint(.BrandBlue)
                }
            }
        }
    }

    /// iOS extras: UPI pay QR / link (when a company VPA is configured) and the contact update
    /// (caller / head office records the customer's latest phone / address — notifies the FOS).
    @ViewBuilder private var extrasRow: some View {
        let upi: Bool = canPay && hasUpi
        if upi || canUpdateContact {
            HStack(spacing: 8) {
                if upi {
                    Button(action: onUpi) {
                        Label("UPI QR / link", systemImage: "qrcode")
                            .font(.system(size: 13, weight: .medium))
                            .frame(maxWidth: .infinity, minHeight: 36)
                    }
                    .buttonStyle(.bordered).tint(.BrandBlue)
                }
                if canUpdateContact {
                    Button(action: onContactUpdate) {
                        Label("Update contact", systemImage: "square.and.pencil")
                            .font(.system(size: 13, weight: .medium))
                            .frame(maxWidth: .infinity, minHeight: 36)
                    }
                    .buttonStyle(.bordered).tint(.BrandBlue)
                }
            }
        }
    }

    /// A pincode/city-level pin can be kilometres off — search the address text instead.
    private func navigate() {
        let rough: Bool = c.locationSource != "field" && (c.geoPrecision == "pincode" || c.geoPrecision == "city")
        if c.latitude == nil || rough {
            let q: String = [c.address, c.pincode].compactMap { $0 }.joined(separator: ", ")
            Actions.mapsSearch(q)
        } else {
            Actions.navigate(lat: c.latitude, lng: c.longitude, address: c.customerName)
        }
    }
}

/// Outlined icon-over-label button (Kotlin ActionBtn).
struct DetailIconButton: View {
    let label: String
    let systemImage: String
    let action: () -> Void

    init(label: String, systemImage: String, action: @escaping () -> Void) {
        self.label = label
        self.systemImage = systemImage
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 3) {
                Image(systemName: systemImage).font(.system(size: 17))
                Text(label).font(.labelSmall).lineLimit(1)
            }
            .foregroundColor(.BrandBlue)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.BrandBlue.opacity(0.35), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Detail fields

struct DetailFieldsView: View {
    let c: Case

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if CaseText.nb(c.newPhone) != nil || CaseText.nb(c.newAddress) != nil {
                SectionTitle("🆕 Latest customer contact")
                LatestContactCard(c: c)
            }
            SectionTitle("Customer")
            InfoCard {
                DetailField("Name", c.customerName)
                DetailField("Phone", c.phone)
                DetailField("Alt phone", c.altPhone)
                DetailField("Card no", c.cardNo)
                DetailField("Account no", c.accountNo)
                DetailAddressBlock(c: c)
            }
            SectionTitle("Account")
            accountCard
            SectionTitle("Recovery (MIS)")
            recoveryCard
            SectionTitle("Status")
            statusCard
        }
    }

    private var accountCard: some View {
        InfoCard {
            Group {
                DetailField("Bank", c.bank)
                DetailField("Branch", c.branch)
                DetailField("Product", c.product)
                DetailField("Bucket", c.bucket)
                DetailField("Cycle", c.cycle)
                DetailField("Month", c.period ?? c.month)
            }
            DetailField("Total outstanding", CaseText.money(c.totalOutstanding))
            DetailField("Principal", CaseText.money(c.principalOutstanding))
            DetailField("Min due", CaseText.money(c.minAmountDue))
            if c.fundingAmount > 0 {
                DetailField("Funding target", CaseText.money(c.fundingAmount))
            }
            DetailField("Received", CaseText.money(c.receivedAmount))
            DetailField("Pending", CaseText.money(CaseText.pending(c)))
        }
    }

    private var showPendingSettlement: Bool {
        return c.isSettlementCase && (c.paidStatus ?? "").uppercased() != "PAID"
    }

    private var recoveryCard: some View {
        InfoCard {
            DetailField("Segment", c.segment)
            DetailField("ENR", c.enr > 0 ? CaseText.money(c.enr) : nil)
            DetailField("NORM amount", c.normAmount > 0 ? CaseText.money(c.normAmount) : nil)
            DetailField("STAB amount", c.stabAmount > 0 ? CaseText.money(c.stabAmount) : nil)
            if showPendingSettlement {
                DetailField("Pending NORM", c.remainingToNorm.flatMap { (v: Double) -> String? in CaseText.money(v) })
                DetailField("Pending STAB", c.remainingToStab.flatMap { (v: Double) -> String? in CaseText.money(v) })
            }
            DetailField("Paid at (NORM/STAB)", c.normStab)
            if c.autoDebit {
                DetailField("Payment type", "⚡ Auto-debit / e-NACH — PAID (cash not counted)")
            }
            DetailField("Caller", c.callerName)
            DetailField("Field agent (FOS)", c.fosName)
            DetailField("Joint FOS", jointText)
        }
    }

    private var jointText: String? {
        let s: String = [CaseText.nb(c.jointFosName), CaseText.nb(c.jointNote)].compactMap { $0 }.joined(separator: " · ")
        return s.isEmpty ? nil : s
    }

    private var locationText: String? {
        guard let la = c.latitude, let lo = c.longitude else { return nil }
        return CaseText.coord(la, 5) + ", " + CaseText.coord(lo, 5)
    }

    private var statusCard: some View {
        InfoCard {
            DetailField("Status", c.status)
            DetailField("Paid status", c.paidStatus)
            DetailField("Disposition", c.disposition)
            DetailField("Follow-up", c.followUpDate.map { DateUtil.humanDate($0) })
            DetailField("Remarks", c.remarks)
            DetailField("Location", locationText)
        }
    }
}

/// Latest address / phone a caller or head-office found mid-cycle — highlighted for the FOS.
private struct LatestContactCard: View {
    let c: Case

    var body: some View {
        InfoCard {
            if let by = CaseText.nb(c.newContactBy) {
                Text("Updated by " + by).font(.labelSmall).foregroundColor(.MutedDim)
            }
            if let p = CaseText.nb(c.newPhone) {
                Text("📞 " + p).font(.system(size: 14, weight: .semibold)).foregroundColor(.BrandBlue)
                HStack(spacing: 8) {
                    Button("Call") { Actions.dial(p) }.buttonStyle(.bordered).tint(.BrandBlue)
                    Button("WhatsApp") { Actions.whatsApp(p) }.buttonStyle(.bordered).tint(.BrandBlue)
                }
                .padding(.top, 4)
            }
            if let a = CaseText.nb(c.newAddress) {
                Spacer().frame(height: 8)
                Text("📍 " + a).font(.bodyMedium).foregroundColor(.TextDark)
                Button("🔍 Search in Maps") { Actions.mapsSearch(a) }
                    .buttonStyle(.bordered).tint(.BrandBlue)
                    .padding(.top, 4)
            }
        }
    }
}

/// One label/value row; hidden when the value is blank (Kotlin Field).
struct DetailField: View {
    let label: String
    let value: String?

    init(_ label: String, _ value: String?) {
        self.label = label
        self.value = value
    }

    var body: some View {
        if let v = CaseText.nb(value) {
            HStack(alignment: .top, spacing: 8) {
                Text(label).font(.bodySmall).foregroundColor(.MutedDim)
                    .frame(width: 128, alignment: .leading)
                Text(v).font(.system(size: 14, weight: .medium)).foregroundColor(.TextDark)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.vertical, 3)
        }
    }
}

// MARK: - Addresses (up to 3, each with its own pincode, pin precision note and Navigate / Search)

private struct DetailAddr: Identifiable {
    let id: Int
    let label: String
    let addr: String?
    let pin: String?
    let lat: Double?
    let lng: Double?
    let prec: String?
}

struct DetailAddressBlock: View {
    let c: Case

    private var rows: [DetailAddr] {
        let all: [DetailAddr] = [
            DetailAddr(id: 1, label: "Address 1", addr: c.address, pin: c.pincode, lat: c.latitude, lng: c.longitude,
                       prec: c.locationSource == "field" ? "field" : c.geoPrecision),
            DetailAddr(id: 2, label: "Address 2", addr: c.address2, pin: c.pincode2, lat: c.latitude2, lng: c.longitude2,
                       prec: c.geoPrecision2),
            DetailAddr(id: 3, label: "Address 3", addr: c.address3, pin: c.pincode3, lat: c.latitude3, lng: c.longitude3,
                       prec: c.geoPrecision3),
        ]
        return all.filter { CaseText.nb($0.addr) != nil || CaseText.nb($0.pin) != nil }
    }

    var body: some View {
        let list: [DetailAddr] = rows
        if list.isEmpty {
            DetailField("Address", nil)
        } else {
            ForEach(list) { r in
                row(r, multi: list.count > 1)
            }
        }
    }

    private func pinNote(_ r: DetailAddr) -> String? {
        switch r.prec {
        case nil: return r.lat == nil ? "Not on map yet — use Search" : nil
        case "field"?: return "📍 Pin confirmed at doorstep"
        case "rooftop"?: return "📍 Pin: building"
        case "street"?: return "📍 Pin: street"
        case "locality"?: return "📍 Pin: area only — Search may be closer"
        case "pincode"?: return "⚠ Pin: pincode centre only — use Search"
        case "city"?: return "⚠ Pin: city only — use Search"
        default: return nil
        }
    }

    private func row(_ r: DetailAddr, multi: Bool) -> some View {
        let label: String = multi ? r.label : "Address"
        let textParts: [String] = [CaseText.nb(r.addr), CaseText.nb(r.pin).map { "(" + $0 + ")" }].compactMap { $0 }
        let text: String = textParts.joined(separator: " ")
        let query: String = [CaseText.nb(r.addr), CaseText.nb(r.pin)].compactMap { $0 }.joined(separator: ", ")
        let note: String? = pinNote(r)
        return VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.bodySmall).foregroundColor(.MutedDim)
            Text(text.isEmpty ? "—" : text).font(.system(size: 14, weight: .medium)).foregroundColor(.TextDark)
            if let n = note {
                Text(n).font(.labelSmall).foregroundColor(.MutedDim)
            }
            HStack(spacing: 8) {
                if let la = r.lat, let lo = r.lng {
                    Button(action: { Actions.navigate(lat: la, lng: lo, address: c.customerName) }) {
                        Text("🧭 Navigate to pin").font(.system(size: 13, weight: .medium)).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered).tint(.BrandBlue)
                }
                Button(action: { Actions.mapsSearch(query) }) {
                    Text("🔍 Search in Maps").font(.system(size: 13, weight: .medium)).frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered).tint(.BrandBlue)
            }
            .padding(.top, 4)
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Timeline

struct DetailTimelineRow: View {
    let e: TimelineEvent

    private var dotColor: Color {
        switch e.type {
        case "payment": return .Good
        case "visit": return .BrandBlue
        case "call": return Color(argb: 0xFFD97706)
        default: return .MutedDim
        }
    }

    private var fresh: Bool {
        guard let d = DateUtil.parseTimestamp(e.at) else { return false }
        let age: TimeInterval = Date().timeIntervalSince(d)
        return age >= 0 && age < 24.0 * 3600.0
    }

    var body: some View {
        let isFresh: Bool = fresh
        HStack(alignment: .top, spacing: 10) {
            Circle().fill(dotColor).frame(width: 10, height: 10).padding(.top, 4)
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .top) {
                    Text(e.title + (isFresh ? "  🆕" : ""))
                        .font(.system(size: 14, weight: .semibold)).foregroundColor(.TextDark)
                    Spacer(minLength: 6)
                    Text(DateUtil.humanTime(e.at)).font(.labelSmall).foregroundColor(.MutedDim)
                }
                if let d = CaseText.nb(e.detail) {
                    Text(d).font(.bodySmall).foregroundColor(.Muted)
                }
                if let a = e.amount, a > 0.0 {
                    Text(inr(a)).font(.labelMedium).foregroundColor(.Good)
                }
                if let by = CaseText.nb(e.by) {
                    Text("by " + by).font(.labelSmall).foregroundColor(.MutedDim)
                }
            }
        }
        .padding(isFresh ? 6 : 0)
        .background(RoundedRectangle(cornerRadius: 8).fill(isFresh ? Color.Warn.opacity(0.12) : Color.clear))
    }
}
