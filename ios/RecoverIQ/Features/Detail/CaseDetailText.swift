import Foundation

// Plain-text / data helpers for the case detail screen and the visit form
// (port of the private helpers in ui/detail/CaseDetailScreen.kt + VisitDialog.kt data classes).

/// One of the customer's addresses the FOS can say he visited (Kotlin VisitAddress).
struct VisitAddress: Hashable, Identifiable {
    let key: String      // "1" / "2" / "3" / "new"
    let label: String
    let text: String
    var id: String { key }
}

/// Result payload of the visit form (Kotlin VisitDraft) — uploaded via API.createVisit(...).
struct VisitDraft {
    var lat: Double?
    var lng: Double?
    var accuracy: Double?
    var personMoved: Bool
    var paid: Bool
    var amount: Double
    var disposition: String?
    var note: String?
    var photoJpeg: Data?
    var normStab: String? = nil
    var ptpDate: String? = nil
    var paymentPhotoJpeg: Data? = nil
    var addressSlot: String? = nil
    var addressText: String? = nil
    var gpsMock: Bool = false
    var gpsFixAgeS: Double? = nil
    var gpsPincode: String? = nil
    var gpsAddress: String? = nil
    var gpsCity: String? = nil
}

enum CaseText {

    /// Non-blank trimmed string or nil.
    static func nb(_ s: String?) -> String? {
        guard let v = s?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty else { return nil }
        return v
    }

    /// CC & PL/BL sheets have no FUNDING AMOUNT, so base pending on TOS (then ENR).
    static func payBase(_ c: Case) -> Double {
        if c.fundingAmount > 0 { return c.fundingAmount }
        if c.totalOutstanding > 0 { return c.totalOutstanding }
        return c.enr
    }

    /// Pending = base − received, never negative.
    static func pending(_ c: Case) -> Double {
        return max(payBase(c) - c.receivedAmount, 0.0)
    }

    /// Kotlin `money(v)`: "₹1,23,456" when > 0 else nil.
    static func money(_ v: Double) -> String? {
        return v > 0.0 ? inr(v) : nil
    }

    static func rs(_ v: Double) -> String { return "Rs " + indianGrouped(v) }

    static func coord(_ v: Double, _ digits: Int) -> String {
        return String(format: "%.\(digits)f", v)
    }

    /// The customer's addresses the FOS can choose from in the visit form (only non-blank ones).
    static func visitAddresses(_ c: Case) -> [VisitAddress] {
        var out: [VisitAddress] = []
        if let a = nb(c.address) { out.append(VisitAddress(key: "1", label: "Address 1", text: a)) }
        if let a = nb(c.address2) { out.append(VisitAddress(key: "2", label: "Address 2", text: a)) }
        if let a = nb(c.address3) { out.append(VisitAddress(key: "3", label: "Address 3", text: a)) }
        if let a = nb(c.newAddress) { out.append(VisitAddress(key: "new", label: "New address", text: a)) }
        return out
    }

    static func accuracyQuality(_ m: Double) -> String {
        if m <= 10 { return "Excellent" }
        if m <= 30 { return "Good" }
        if m <= 100 { return "Fair" }
        return "Weak"
    }

    /// WhatsApp caption for a just-logged visit (Kotlin buildVisitMessage).
    static func visitMessage(_ c: Case, agentName: String, draft v: VisitDraft) -> String {
        var lines: [String] = []
        lines.append("🧾 SSD Enterprises — Field visit logged")
        lines.append("Customer: " + (c.customerName ?? "—"))
        if let p = c.phone { lines.append("Phone: " + p) }
        if let p = c.cardNo { lines.append("Card no: " + p) }
        if let p = c.accountNo { lines.append("A/C no: " + p) }
        let portfolio: String = [nb(c.bank), nb(c.product), nb(c.segment)].compactMap { $0 }.joined(separator: " · ")
        if !portfolio.isEmpty { lines.append("Portfolio: " + portfolio) }
        if let cy = nb(c.cycle) { lines.append("CYC: " + cy) }
        if let bk = nb(c.bucket) { lines.append("BKT: " + bk) }
        if c.enr > 0 {
            lines.append("ENR: " + inr(c.enr))
        } else if c.totalOutstanding > 0 {
            lines.append("TOS: " + inr(c.totalOutstanding))
        }
        let addrs: [VisitAddress] = visitAddresses(c)
        let picked: VisitAddress? = addrs.first(where: { $0.key == v.addressSlot }) ?? addrs.first
        if let a = picked {
            var pin: String? = nil
            switch a.key {
            case "1": pin = c.pincode
            case "2": pin = c.pincode2
            case "3": pin = c.pincode3
            default: pin = nil
            }
            var withPin: String = a.text
            if let p = nb(pin), !a.text.contains(p) { withPin = a.text + ", " + p }
            lines.append("Visited (" + a.label + "): " + withPin)
        }
        if v.gpsAddress != nil || v.gpsPincode != nil {
            var acc: String = ""
            if let m = v.accuracy {
                acc = " · GPS ±" + String(Int(m)) + " m (" + accuracyQuality(m) + ")"
            }
            lines.append("Detected at photo: " + (v.gpsAddress ?? "—") + " · PIN " + (v.gpsPincode ?? "—") + acc)
        }
        lines.append("Outcome: " + (v.disposition ?? "—"))
        if v.paid && v.amount > 0 { lines.append("Collected: " + inr(v.amount)) }
        if v.personMoved { lines.append("⚠ Person has moved") }
        if let n = v.note { lines.append("Note: " + n) }
        if let la = v.lat, let lo = v.lng {
            lines.append("Location: " + coord(la, 5) + ", " + coord(lo, 5))
            lines.append("Map: https://maps.google.com/?q=" + String(la) + "," + String(lo))
        }
        lines.append("Agent: " + agentName)
        return lines.joined(separator: "\n")
    }

    // MARK: - Clipboard texts

    private static func line(_ label: String, _ v: String?) -> String? {
        guard let s = nb(v) else { return nil }
        return label + ": " + s
    }

    private static func addr(_ a: String?, _ pin: String?) -> String? {
        let parts: [String] = [nb(a), nb(pin).map { "PIN " + $0 }].compactMap { $0 }
        let s = parts.joined(separator: " - ")
        return s.isEmpty ? nil : s
    }

    private static func joinNB(_ parts: [String?], _ sep: String) -> String? {
        let s = parts.compactMap { nb($0) }.joined(separator: sep)
        return s.isEmpty ? nil : s
    }

    /// Tap copy: key case info (Kotlin caseInfoText).
    static func infoText(_ c: Case) -> String {
        var rows: [String?] = []
        rows.append(line("Customer", c.customerName))
        rows.append(line("Account", c.accountNo))
        rows.append(line("Card", c.cardNo))
        rows.append(line("Phone", c.phone))
        rows.append(line("Alt phone", c.altPhone))
        rows.append(line("New phone", c.newPhone))
        rows.append(line("Bank / Product", joinNB([c.bank, c.product], " / ")))
        let bcm: String? = joinNB([c.bucket.map { "Bkt " + $0 }, c.cycle.map { "Cyc " + $0 }, c.period ?? c.month], " | ")
        rows.append(line("Bucket / Cycle / Month", bcm))
        rows.append("Pending: " + rs(c.pendingAmount) + "   Received: " + rs(c.receivedAmount))
        var tos: String = "TOS: " + rs(c.totalOutstanding) + "   NORM: " + rs(c.normAmount) + "   STAB: " + rs(c.stabAmount)
        if let ns = nb(c.normStab) { tos += "   N/S: " + ns }
        rows.append(tos)
        rows.append(line("Status", c.paidStatus ?? c.status))
        rows.append(line("Disposition", c.disposition))
        rows.append(line("PTP / follow-up", c.followUpDate))
        rows.append(line("Address 1", addr(c.address, c.pincode)))
        rows.append(line("Address 2", addr(c.address2, c.pincode2)))
        rows.append(line("Address 3", addr(c.address3, c.pincode3)))
        rows.append(line("New address", c.newAddress))
        rows.append(line("FOS", c.assignedFosName ?? c.fosName))
        rows.append(line("Caller", c.assignedCallerName ?? c.callerName))
        rows.append(line("Remarks", c.remarks))
        return rows.compactMap { $0 }.joined(separator: "\n")
    }

    private static func rsOpt(_ v: Double?) -> String? { return v.map { rs($0) } }
    private static func moneyNZ(_ v: Double) -> String? { return v == 0.0 ? nil : rs(v) }
    private static func yn(_ b: Bool?) -> String? { return b == true ? "Yes" : nil }
    private static func mapLink(_ lat: Double?, _ lng: Double?) -> String? {
        guard let la = lat, let lo = lng else { return nil }
        return "https://maps.google.com/?q=" + String(la) + "," + String(lo)
    }

    private static func sec(_ title: String, _ rows: [(String, String?)]) -> String? {
        let body: String = rows.compactMap { (r: (String, String?)) -> String? in
            guard let v = nb(r.1) else { return nil }
            return r.0 + ": " + v
        }.joined(separator: "\n")
        return body.isEmpty ? nil : "— " + title + " —\n" + body
    }

    /// Double-tap copy: every field the app has for the case (Kotlin caseFullText).
    static func fullText(_ c: Case) -> String {
        var out: [String?] = []
        out.append(sec("CUSTOMER", [
            ("Case ID", String(c.id)),
            ("Customer", c.customerName),
            ("Account", c.accountNo),
            ("Card", c.cardNo),
            ("Phone", c.phone),
            ("Alt phone", c.altPhone),
            ("New phone", c.newPhone),
            ("New contact by", joinNB([c.newContactBy, c.newContactAt], " · ")),
        ]))
        out.append(sec("PORTFOLIO", [
            ("Bank", c.bank), ("Product", c.product), ("Segment", c.segment), ("Branch", c.branch),
            ("Bucket", c.bucket), ("Cycle", c.cycle), ("Month", c.period ?? c.month), ("Category", c.cat),
        ]))
        out.append(sec("AMOUNTS", [
            ("TOS", rs(c.totalOutstanding)),
            ("Principal (POS)", moneyNZ(c.principalOutstanding)),
            ("Min amount due", moneyNZ(c.minAmountDue)),
            ("Funding", moneyNZ(c.fundingAmount)),
            ("ENR", moneyNZ(c.enr)),
            ("NORM", rs(c.normAmount)),
            ("STAB", rs(c.stabAmount)),
            ("N/S", c.normStab),
            ("Pending NORM", rsOpt(c.remainingToNorm)),
            ("Pending STAB", rsOpt(c.remainingToStab)),
            ("Received", rs(c.receivedAmount)),
            ("Pending", rs(c.pendingAmount)),
            ("Settlement case", yn(c.isSettlementCase)),
            ("Auto-debit", yn(c.autoDebit)),
        ]))
        out.append(sec("STATUS", [
            ("Status", c.status), ("Paid status", c.paidStatus), ("Disposition", c.disposition),
            ("PTP / follow-up", c.followUpDate), ("Last contacted", c.lastContactedAt),
            ("Visited", yn(c.visited)), ("Escalated", yn(c.escalated)),
            ("Flag", c.flagReason ?? yn(c.flagged)),
            ("Propensity", c.propensity.map { String($0) }),
            ("My note", c.reviewNote), ("Remarks", c.remarks),
        ]))
        out.append(sec("ADDRESSES", [
            ("Address 1", joinNB([c.address, c.pincode.map { "PIN " + $0 }], " - ")),
            ("Map 1", mapLink(c.latitude, c.longitude)),
            ("Address 2", joinNB([c.address2, c.pincode2.map { "PIN " + $0 }], " - ")),
            ("Map 2", mapLink(c.latitude2, c.longitude2)),
            ("Address 3", joinNB([c.address3, c.pincode3.map { "PIN " + $0 }], " - ")),
            ("Map 3", mapLink(c.latitude3, c.longitude3)),
            ("New address", c.newAddress),
            ("DIGIPIN", c.digipin),
        ]))
        out.append(sec("TEAM", [
            ("FOS", joinNB([c.assignedFosName ?? c.fosName, c.assignedFosCode, c.assignedFosPhone], " · ")),
            ("Caller", joinNB([c.assignedCallerName ?? c.callerName, c.assignedCallerCode, c.assignedCallerPhone], " · ")),
            ("Joint FOS", joinNB([c.jointFosName, c.jointNote], " · ")),
            ("Team", c.team), ("Team lead", c.teamLead),
        ]))
        return out.compactMap { $0 }.joined(separator: "\n\n")
    }

    /// Readable error for a failed submit (Kotlin: server detail, else network hint, else message).
    static func submitError(_ e: Error) -> String {
        if let api = e as? APIError {
            if let d = nb(api.detail) { return d }
            if case .network = api {
                return "Couldn't submit — check your signal and tap Save again. Your entry is kept."
            }
            return api.localizedDescription + " Your entry is kept."
        }
        if e is URLError {
            return "Couldn't submit — check your signal and tap Save again. Your entry is kept."
        }
        return e.localizedDescription + " Your entry is kept."
    }
}
