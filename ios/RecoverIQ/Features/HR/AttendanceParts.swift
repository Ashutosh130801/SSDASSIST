import SwiftUI

// Sub-views + formatting helpers for AttendanceView (AttendanceScreens.kt: Kpi, AttCard, PresenceChip, matrix).

enum AttFmt {
    static func fmtDur(_ sec: Int) -> String {
        let s: Int = max(0, sec)
        let h: Int = s / 3600
        let m: Int = (s % 3600) / 60
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }

    /// API timestamps are UTC (naive on SQLite). Treat as UTC and render in IST "hh:mm a".
    static func hhmm(_ iso: String?) -> String {
        guard let raw = iso, !raw.trimmingCharacters(in: .whitespaces).isEmpty else { return "—" }
        var core: String = raw
        if let i = core.firstIndex(of: "+") { core = String(core[..<i]) }
        if let i = core.firstIndex(of: "Z") { core = String(core[..<i]) }
        core = core.replacingOccurrences(of: "T", with: " ")
        core = String(core.prefix(19))
        let pat: String = core.count > 16 ? "yyyy-MM-dd HH:mm:ss" : (core.count > 10 ? "yyyy-MM-dd HH:mm" : "yyyy-MM-dd")
        let inF = DateFormatter()
        inF.locale = Locale(identifier: "en_US_POSIX")
        inF.timeZone = DateUtil.utc
        inF.dateFormat = pat
        guard let d = inF.date(from: core) else { return "—" }
        let out = DateFormatter()
        out.locale = Locale(identifier: "en_US_POSIX")
        out.timeZone = DateUtil.ist
        out.dateFormat = "hh:mm a"
        return out.string(from: d)
    }

    static func money(_ v: Double) -> String { "₹" + HRUtil.grouped(v, decimals: 0) }

    static func dayUnits(_ v: JSONValue?) -> String {
        let n: Double = v?.double ?? 0.0
        if n == n.rounded() && abs(n) < 1e9 { return String(Int(n)) }
        return "\(n)"
    }

    static func letterColor(_ v: String) -> Color {
        switch v {
        case "HD", "H•": return Color(argb: 0xFF7C3AED)
        case "H": return Color(argb: 0xFFEA580C)
        case "P": return .Good
        case "L": return .Warn
        case "LV": return .BrandBlue
        case "A": return Color(argb: 0xFFDC2626)
        default: return .MutedDim
        }
    }

    static func presenceColor(_ state: String) -> Color {
        switch state {
        case "active": return .Good
        case "idle": return .Warn
        default: return .MutedDim
        }
    }

    static func openMap(lat: Double, lng: Double) {
        let s: String = "https://maps.google.com/?q=\(lat),\(lng)"
        if !Actions.open("comgooglemaps://?q=\(lat),\(lng)") {
            if !Actions.open(s) { _ = Actions.open("http://maps.apple.com/?q=\(lat),\(lng)") }
        }
    }
}

/// Kotlin `PresenceChip`: coloured dot + "Active on mobile/web" / "Idle 5m" / "Offline".
struct AttPresenceChip: View {
    let p: AttPresence

    private var label: String {
        let plat: String = (p.platform == "android" || p.platform == "ios") ? "mobile" : "web"
        switch p.state {
        case "active": return "Active on \(plat)"
        case "idle": return "Idle" + (p.idleSeconds > 60 ? " " + AttFmt.fmtDur(p.idleSeconds) : "")
        default: return "Offline"
        }
    }

    var body: some View {
        let c: Color = AttFmt.presenceColor(p.state)
        HStack(spacing: 5) {
            Circle().fill(c).frame(width: 8, height: 8)
            Text(label).font(.labelSmall.weight(.semibold)).foregroundColor(c)
        }
    }
}

struct AttKpi: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        InfoCard(spacing: 2, padding: 12) {
            Text(value).font(.titleLarge.weight(.bold)).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(label).font(.labelSmall).foregroundColor(.Muted).lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }
}

/// One person's day row (Kotlin AttCard).
struct AttCard: View {
    let r: AttRow

    private var half: Bool { r.halfDayLeave || r.status == "half_leave" }
    private var lateHalf: Bool { r.status == "half_day" }

    private var statusColor: Color {
        if half { return Color(argb: 0xFF7C3AED) }
        if lateHalf { return Color(argb: 0xFFEA580C) }
        if r.status == "leave" { return .BrandBlue }
        if r.late { return .Warn }
        if r.status == "present" { return .Good }
        if r.status == "absent" { return Color(argb: 0xFFDC2626) }
        return .MutedDim
    }

    private var statusText: String {
        if half { return "Half-day leave (approved)" }
        if lateHalf { return "Half day (checked in after 11:30)" }
        if r.status == "leave" { return "Leave" }
        if r.late { return "Present (late)" }
        return r.status.prefix(1).uppercased() + String(r.status.dropFirst())
    }

    private var idLine: String {
        var parts: [String] = []
        if let c = r.empCode { parts.append(c) }
        if let ro = r.role { parts.append(ro) }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        InfoCard(spacing: 4) {
            HStack(alignment: .top) {
                leftColumn
                Spacer(minLength: 8)
                rightColumn
            }
            activityRow.padding(.top, 4)
            liveRow
        }
    }

    private var leftColumn: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(r.name ?? "—").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
            Text(idLine).font(.labelSmall).foregroundColor(.Muted)
            AttPresenceChip(p: r.presence)
        }
    }

    private var rightColumn: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(statusText).font(.labelMedium.weight(.bold)).foregroundColor(statusColor)
                .multilineTextAlignment(.trailing)
            if half {
                Text("\(AttFmt.dayUnits(JSONValue.double(r.leaveDays))) leave · \(AttFmt.dayUnits(JSONValue.double(r.presentDays))) present · \(AttFmt.dayUnits(JSONValue.double(r.absentDays))) absent")
                    .font(.labelSmall).foregroundColor(.Muted)
            }
            Text("In \(AttFmt.hhmm(r.checkInAt)) · Out \(AttFmt.hhmm(r.checkOutAt))")
                .font(.labelSmall).foregroundColor(.Muted)
            Text("Worked \(AttFmt.fmtDur(r.workedSeconds)) · Idle \(AttFmt.fmtDur(r.idleSeconds))")
                .font(.labelSmall).foregroundColor(.MutedDim)
        }
    }

    private var activityRow: some View {
        HStack(spacing: 12) {
            if r.showActivity {
                Text("📞 \(r.calls)\(r.teamTotal ? " (team)" : "")").font(.labelSmall).foregroundColor(.Muted)
                Text("🧍 \(r.visits)").font(.labelSmall).foregroundColor(.Muted)
                Text("💰 \(AttFmt.money(r.collected))").font(.labelSmall).foregroundColor(.Good)
            }
            if let la = r.checkInLat, let ln = r.checkInLng {
                Text("📍 " + String(format: "%.4f", la) + ", " + String(format: "%.4f", ln))
                    .font(.labelSmall).foregroundColor(.BrandBlue)
                    .onTapGesture { AttFmt.openMap(lat: la, lng: ln) }
            }
        }
    }

    @ViewBuilder private var liveRow: some View {
        if r.role == "fos", let la = r.liveLat, let ln = r.liveLng {
            Text("🛰 Live · \(AttFmt.hhmm(r.liveAt)) · tap to track")
                .font(.labelSmall.weight(.semibold)).foregroundColor(.Good)
                .padding(.top, 2)
                .onTapGesture { AttFmt.openMap(lat: la, lng: ln) }
        }
    }
}

/// Monthly / cycle matrix: Name | one column per day | P L H LV A H• Hrs. Horizontally scrollable.
struct AttMonthMatrix: View {
    let days: [String]
    let people: [[String: JSONValue]]

    private var totals: [String] { ["P", "L", "H", "LV", "A", "H•", "Hrs"] }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 0) {
                header
                ForEach(0..<people.count, id: \.self) { i in
                    personRow(people[i]).padding(.vertical, 2)
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 0) {
            cell("Name", width: 120, color: .BrandBlue, bold: true)
            ForEach(days, id: \.self) { d in
                cell(String(d.suffix(2)), width: 22, color: .Muted, bold: true)
            }
            ForEach(totals, id: \.self) { h in
                cell(h, width: 34, color: .BrandBlue, bold: true)
            }
        }
    }

    private func personRow(_ p: [String: JSONValue]) -> some View {
        let pd: [String: JSONValue] = p.obj("days")
        let hours: Double = p.dbl("worked_hours") ?? 0.0
        return HStack(spacing: 0) {
            Text(p.str("name") ?? "—").font(.labelSmall.weight(.medium)).foregroundColor(.TextDark)
                .lineLimit(1).frame(width: 120, alignment: .leading)
            ForEach(days, id: \.self) { d in
                let v: String = pd[d]?.text ?? ""
                cell(v, width: 22, color: AttFmt.letterColor(v), bold: true)
            }
            cell(AttFmt.dayUnits(p["present"]), width: 34, color: .TextDark, bold: false)
            cell("\(p.int("late") ?? 0)", width: 34, color: .Warn, bold: false)
            cell("\(p.int("late_half_days") ?? 0)", width: 34, color: Color(argb: 0xFFEA580C), bold: false)
            cell(AttFmt.dayUnits(p["leave"]), width: 34, color: .BrandBlue, bold: false)
            cell(AttFmt.dayUnits(p["absent"]), width: 34, color: Color(argb: 0xFFDC2626), bold: false)
            cell("\(p.int("half_days") ?? 0)", width: 34, color: Color(argb: 0xFF7C3AED), bold: false)
            cell("\(hours)", width: 34, color: .TextDark, bold: false)
        }
    }

    private func cell(_ text: String, width: CGFloat, color: Color, bold: Bool) -> some View {
        Text(text)
            .font(bold ? Font.labelSmall.weight(.bold) : Font.labelSmall)
            .foregroundColor(color)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .frame(width: width, alignment: .leading)
    }
}
