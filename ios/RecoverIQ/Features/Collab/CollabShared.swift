import SwiftUI
import UIKit

// Shared helpers for the Collab group — port of the private helpers at the top of
// ui/common/CollabScreens.kt (generic-map accessors, roleLabel, chatWhen, Kpi).

// MARK: - Generic-map helpers (Kotlin Any?.m() / .l() / .d() / .i() / .s())

extension Optional where Wrapped == JSONValue {
    /// Kotlin `.m()` — object or empty.
    var cm: [String: JSONValue] { self?.object ?? [:] }
    /// Kotlin `.l()` — array or empty.
    var cl: [JSONValue] { self?.array ?? [] }
    /// Kotlin `.d()` — number or 0.0.
    var cd: Double { self?.double ?? 0.0 }
    /// Kotlin `.i()` — number or 0.
    var ci: Int { self?.int ?? 0 }
    /// Kotlin `.s()` — display string or "".
    var cs: String { self?.text ?? "" }
    /// Kotlin `x == true`.
    var cTrue: Bool {
        if case .some(.bool(let b)) = self { return b }
        return false
    }
    /// Kotlin `x as? String` (only real strings, nil otherwise).
    var cStr: String? {
        if case .some(.string(let s)) = self { return s }
        return nil
    }
    /// Kotlin `x as? Number` → Int.
    var cNum: Int? {
        switch self {
        case .some(.int(let i)): return i
        case .some(.double(let d)): return d.isFinite ? Int(d) : nil
        default: return nil
        }
    }
}

extension JSONValue {
    var cm: [String: JSONValue] { object ?? [:] }
}

/// Kotlin roleLabel(r) from CollabScreens.kt.
func collabRoleLabel(_ r: String) -> String {
    switch r {
    case "fos": return "Field Agent"
    case "telecaller": return "Tele-caller"
    case "teamlead": return "Team Lead"
    case "manager": return "Manager"
    case "headoffice": return "Head Office"
    case "backend": return "Back Office"
    case "hr": return "HR"
    case "admin": return "Admin"
    default:
        if r.isEmpty { return r }
        return r.prefix(1).uppercased() + String(r.dropFirst())
    }
}

/// WhatsApp-style short time for the chat list ("now", "9:41 AM", "Mon", "12 Aug").
func chatWhen(_ iso: String?) -> String {
    guard let s = iso, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return "" }
    guard let t = DateUtil.parseTimestamp(s) else { return "" }
    let now = Date()
    let mins: Double = now.timeIntervalSince(t) / 60.0
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone.current
    let day = DateFormatter()
    day.locale = Locale(identifier: "en_US_POSIX")
    day.timeZone = TimeZone.current
    day.dateFormat = "yyyyMMdd"
    if mins < 1 { return "now" }
    if mins < 1440 && day.string(from: t) == day.string(from: now) {
        f.dateFormat = "h:mm a"
        return f.string(from: t)
    }
    if mins < 10080 {
        f.dateFormat = "EEE"
        return f.string(from: t)
    }
    f.dateFormat = "d MMM"
    return f.string(from: t)
}

/// Kotlin `"${d}%"` on a Double (e.g. 72.5 → "72.5%").
func collabPct(_ v: Double) -> String {
    if v == v.rounded() { return String(format: "%.1f%%", v) }
    return JSONValue.fmt(v) + "%"
}

/// Kotlin private `Kpi(label, value, color)` card — 120pt wide.
struct CollabKpi: View {
    let label: String
    let value: String
    var color: Color = .TextDark

    init(_ label: String, _ value: String, _ color: Color = .TextDark) {
        self.label = label
        self.value = value
        self.color = color
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 11)).foregroundColor(.Muted).lineLimit(1)
            Text(value).font(.system(size: 16, weight: .bold)).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .padding(10)
        .frame(width: 120, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

/// Plain white card used by the Collab lists (Kotlin `Card(containerColor = CardWhite)`).
struct CollabCard<Content: View>: View {
    var padding: CGFloat = 10
    let content: Content

    init(padding: CGFloat = 10, @ViewBuilder content: () -> Content) {
        self.padding = padding
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) { content }
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

/// Outlined text field (Compose OutlinedTextField with optional label).
struct CollabField: View {
    let label: String
    @Binding var text: String
    var keyboard: UIKeyboardType = .default

    init(_ label: String, text: Binding<String>, keyboard: UIKeyboardType = .default) {
        self.label = label
        self._text = text
        self.keyboard = keyboard
    }

    var body: some View {
        TextField(label, text: $text)
            .keyboardType(keyboard)
            .textFieldStyle(.plain)
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
    }
}

/// Compose ExtendedFloatingActionButton ("+ New …"). Placed bottom-LEADING by callers because the
/// app shell already stacks the chat + help buttons on the bottom-trailing corner.
struct CollabExtendedFab: View {
    let title: String
    let action: () -> Void

    init(_ title: String, action: @escaping () -> Void) {
        self.title = title
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: "plus").font(.system(size: 16, weight: .bold))
                Text(title).font(.system(size: 15, weight: .semibold))
            }
            .foregroundColor(.white)
            .padding(.horizontal, 18).padding(.vertical, 14)
            .background(RoundedRectangle(cornerRadius: 16).fill(Color.BrandBlue))
            .shadow(color: Color.black.opacity(0.2), radius: 6, x: 0, y: 3)
        }
        .buttonStyle(.plain)
        .padding(16)
    }
}
