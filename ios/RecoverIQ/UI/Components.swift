import SwiftUI
import UIKit
import Combine

// Port of ui/common/Components.kt (+ the small tag/chip composables from CaseCard.kt).
// Public pieces: inr(), LogoLoader, AsyncContent, SectionTitle, TrendStrip, InfoCard, DataList,
// StatusChip, PaidTag, TouchTag, PersonChip, reviewColorOf(), REVIEW_COLOR_NAMES, Chip, StatTile,
// EmptyState, ErrorView, PrimaryButton, FlowLayout, ToastBanner.

// MARK: - Money formatting

/// Indian digit grouping: 1234567 → "12,34,567".
func indianGrouped(_ v: Double) -> String {
    let neg = v < 0
    let n = Int64(abs(v).rounded())
    var s = String(n)
    if s.count > 3 {
        let last3 = String(s.suffix(3))
        var rest = String(s.dropLast(3))
        var groups: [String] = []
        while rest.count > 2 {
            groups.insert(String(rest.suffix(2)), at: 0)
            rest = String(rest.dropLast(2))
        }
        if !rest.isEmpty { groups.insert(rest, at: 0) }
        s = groups.joined(separator: ",") + "," + last3
    }
    return (neg ? "-" : "") + s
}

/// "₹1,23,456" (no decimals) — Kotlin `"₹" + "%,.0f".format(v)`.
func inr(_ v: Double) -> String { "₹" + indianGrouped(v) }

/// Optional-friendly variant: nil → "—".
func inr(_ v: Double?) -> String { v.map { inr($0) } ?? "—" }

/// "%.1f%%"-style percentage helper.
func pct(_ v: Double, digits: Int = 1) -> String { String(format: "%.\(digits)f%%", v) }

// MARK: - LogoLoader

/// Branded loading indicator — the SSD coin gently coin-flips and pulses (replaces spinners).
struct LogoLoader: View {
    var size: CGFloat = 60
    @State private var flip: Bool = false
    @State private var pulse: Bool = false

    var body: some View {
        logo
            .frame(width: size, height: size)
            .rotation3DEffect(.degrees(flip ? 360 : 0), axis: (x: 0, y: 1, z: 0))
            .scaleEffect(pulse ? 1.03 : 0.9)
            .accessibilityLabel("Loading")
            .onAppear {
                withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) { flip = true }
                withAnimation(.linear(duration: 0.7).repeatForever(autoreverses: true)) { pulse = true }
            }
    }

    @ViewBuilder private var logo: some View {
        if UIImage(named: "ssd_logo") != nil {
            Image("ssd_logo").resizable().scaledToFit()
        } else {
            ZStack {
                Circle().fill(Color.BrandBlue)
                Text("SSD").font(.system(size: size * 0.28, weight: .bold)).foregroundColor(.white)
            }
        }
    }
}

// MARK: - AsyncContent (Kotlin AsyncContent / Load)

private struct AsyncTaskKey: Equatable {
    let key: AnyHashable
    let nonce: Int
}

/// Loads `load` on appear and whenever `key` changes, then renders loading / error(+Retry) / content.
/// `content` gets the value and a `reload` closure. `live: true` also re-loads silently on
/// `Realtime.shared.changed` (Kotlin `AsyncContent(key = rememberLiveKey())`).
///
/// ```
/// AsyncContent(key: refresh, live: true, load: { try await API.shared.legalCases() }) { cases, reload in
///     ForEach(cases) { c in … }
/// }
/// ```
struct AsyncContent<T, Content: View>: View {
    let key: AnyHashable
    let live: Bool
    let load: () async throws -> T
    let content: (T, @escaping () -> Void) -> Content

    @State private var value: T? = nil
    @State private var error: String? = nil
    @State private var nonce: Int = 0
    @State private var loadedKey: AnyHashable? = nil

    init(key: AnyHashable = AnyHashable(0), live: Bool = false,
         load: @escaping () async throws -> T,
         @ViewBuilder content: @escaping (T, @escaping () -> Void) -> Content) {
        self.key = key
        self.live = live
        self.load = load
        self.content = content
    }

    var body: some View {
        Group {
            if let v = value {
                content(v, reload)
            } else if let e = error {
                ErrorView(message: e, retry: reload)
            } else {
                LogoLoader().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: AsyncTaskKey(key: key, nonce: nonce)) { await run() }
        .onReceive(Realtime.shared.changed) { _ in
            if live { reload() }
        }
    }

    private func reload() { nonce += 1 }

    private func run() async {
        if loadedKey != key {          // key changed → show the loader (Kotlin remember(key) reset)
            value = nil
            error = nil
        }
        do {
            let v = try await load()
            value = v
            error = nil
            loadedKey = key
        } catch {
            if error is CancellationError { return }
            if value == nil { self.error = error.localizedDescription }
        }
    }
}

// MARK: - Text / cards

struct SectionTitle: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.TextDark)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// White rounded card with the glass stroke + soft shadow (Kotlin InfoCard). Content is a leading VStack.
struct InfoCard<Content: View>: View {
    let spacing: CGFloat
    let padding: CGFloat
    let content: Content

    init(spacing: CGFloat = 4, padding: CGFloat = 16, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.padding = padding
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: spacing) { content }
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.GlassStroke, lineWidth: 1))
            .shadow(color: Color.black.opacity(0.06), radius: 6, x: 0, y: 2)
    }
}

/// FTD / MTD / LMTD / Overall cash-collected strip (Kotlin TrendStrip).
struct TrendStrip: View {
    let trends: Trends
    var title: String? = nil

    init(trends: Trends, title: String? = nil) {
        self.trends = trends
        self.title = title
    }

    init(_ trends: Trends, _ title: String? = nil) {
        self.trends = trends
        self.title = title
    }

    private var cells: [(String, String, Double)] {
        return [("FTD", "Today", trends.ftd), ("MTD", "This month", trends.mtd),
                ("LMTD", "Last month", trends.lmtd), ("Overall", "Lifetime", trends.overall)]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let t = title {
                Text(t).font(.bodySmall).foregroundColor(.Muted)
            }
            HStack(spacing: 8) {
                ForEach(0..<cells.count, id: \.self) { i in
                    cell(cells[i].0, cells[i].1, cells[i].2)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func cell(_ lbl: String, _ hint: String, _ v: Double) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(lbl).font(.labelSmall).foregroundColor(.Muted)
            Text(hint).font(.system(size: 11)).foregroundColor(.Muted)
            Text(inr(v)).font(.system(size: 14, weight: .semibold))
                .foregroundColor(lbl == "FTD" ? .Good : .TextDark)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

/// Simple list with an empty-state (Kotlin DataList). Wraps rows in a ScrollView + LazyVStack.
struct DataList<T, Row: View>: View {
    let items: [T]
    let emptyText: String
    var padding: CGFloat = 16
    let row: (T) -> Row

    init(items: [T], emptyText: String, padding: CGFloat = 16, @ViewBuilder row: @escaping (T) -> Row) {
        self.items = items
        self.emptyText = emptyText
        self.padding = padding
        self.row = row
    }

    var body: some View {
        if items.isEmpty {
            EmptyState(text: emptyText)
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(0..<items.count, id: \.self) { i in row(items[i]) }
                }
                .padding(padding)
            }
        }
    }
}

// MARK: - Tags / chips (CaseCard.kt)

struct StatusChip: View {
    let status: String?
    init(_ status: String?) { self.status = status }
    init(status: String?) { self.status = status }

    var body: some View {
        let s = (status ?? "new").lowercased()
        let color: Color = (s.contains("paid") || s.contains("resolved")) ? .Good
            : ((s.contains("ptp") || s.contains("callback")) ? .Warn : .BrandBlue)
        let raw = status ?? "New"
        let label = raw.prefix(1).uppercased() + String(raw.dropFirst())
        return Text(label)
            .font(.labelSmall)
            .foregroundColor(color)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 6).fill(color.opacity(0.12)))
    }
}

struct PaidTag: View {
    let paidStatus: String?
    init(_ paidStatus: String?) { self.paidStatus = paidStatus }
    init(paidStatus: String?) { self.paidStatus = paidStatus }

    var body: some View {
        let s = (paidStatus ?? "").uppercased().trimmingCharacters(in: .whitespaces)
        let color: Color = s == "PAID" ? .Good : (s == "PARTIAL" ? .Warn : .Bad)
        return Group {
            if !s.isEmpty { TouchTag(text: s, color: color) }
        }
    }
}

struct TouchTag: View {
    let text: String
    let color: Color
    init(text: String, color: Color) { self.text = text; self.color = color }
    init(_ text: String, _ color: Color) { self.text = text; self.color = color }

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(color)
            .lineLimit(1)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 6).fill(color.opacity(0.15)))
    }
}

/// A tappable person name that opens their performance screen.
struct PersonChip: View {
    let text: String
    let onClick: () -> Void
    init(text: String, onClick: @escaping () -> Void) { self.text = text; self.onClick = onClick }
    init(_ text: String, onClick: @escaping () -> Void) { self.text = text; self.onClick = onClick }

    var body: some View {
        Button(action: onClick) {
            Text(text)
                .font(.labelSmall)
                .foregroundColor(.BrandBlue)
                .lineLimit(1)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(RoundedRectangle(cornerRadius: 6).fill(Color.BrandBlue.opacity(0.10)))
        }
        .buttonStyle(.plain)
    }
}

/// Personal review-highlight colour name → Color (matches the web palette).
func reviewColorOf(_ name: String?) -> Color? {
    switch name ?? "" {
    case "red": return Color(argb: 0xFFEF4444)
    case "amber": return Color(argb: 0xFFF59E0B)
    case "green": return Color(argb: 0xFF22C55E)
    case "blue": return Color(argb: 0xFF3B82F6)
    case "purple": return Color(argb: 0xFF8B5CF6)
    case "pink": return Color(argb: 0xFFEC4899)
    case "grey": return Color(argb: 0xFF94A3B8)
    default: return nil
    }
}

let REVIEW_COLOR_NAMES: [String] = ["red", "amber", "green", "blue", "purple", "pink", "grey"]

/// Compose FilterChip equivalent: `Chip(label: "Paid", selected: f == "paid") { f = "paid" }`.
struct Chip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    init(label: String, selected: Bool, action: @escaping () -> Void) {
        self.label = label
        self.selected = selected
        self.action = action
    }

    init(_ label: String, selected: Bool, action: @escaping () -> Void) {
        self.label = label
        self.selected = selected
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if selected { Image(systemName: "checkmark").font(.system(size: 10, weight: .bold)) }
                Text(label).font(.system(size: 13, weight: .medium)).lineLimit(1)
            }
            .foregroundColor(selected ? .BrandBlueDark : .TextDark)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(Capsule().fill(selected ? Color.PrimaryContainer : Color.CardWhite))
            .overlay(Capsule().stroke(selected ? Color.BrandBlue.opacity(0.5) : Color.StrokeSoft, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

/// KPI tile: small label, big value, optional sub-line.
struct StatTile: View {
    let label: String
    let value: String
    var color: Color = .TextDark
    var sub: String? = nil

    init(label: String, value: String, color: Color = .TextDark, sub: String? = nil) {
        self.label = label
        self.value = value
        self.color = color
        self.sub = sub
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.labelSmall).foregroundColor(.Muted).lineLimit(1)
            Text(value).font(.system(size: 18, weight: .bold)).foregroundColor(color)
                .lineLimit(1).minimumScaleFactor(0.5)
            if let s = sub { Text(s).font(.system(size: 11)).foregroundColor(.MutedDim).lineLimit(1) }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.GlassStroke, lineWidth: 1))
    }
}

struct EmptyState: View {
    let text: String
    var systemImage: String = "tray"

    init(text: String, systemImage: String = "tray") {
        self.text = text
        self.systemImage = systemImage
    }

    init(_ text: String) {
        self.text = text
        self.systemImage = "tray"
    }

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage).font(.system(size: 30)).foregroundColor(.MutedDim)
            Text(text).font(.bodyMedium).foregroundColor(.Muted).multilineTextAlignment(.center)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct ErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Text(message).foregroundColor(.Bad).multilineTextAlignment(.center).font(.bodyMedium)
            Button("Retry", action: retry).buttonStyle(.borderedProminent).tint(.BrandBlue)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Full-width brand button with an inline spinner while `busy`.
struct PrimaryButton: View {
    let title: String
    var busy: Bool = false
    var enabled: Bool = true
    var color: Color = .BrandBlue
    let action: () -> Void

    init(title: String, busy: Bool = false, enabled: Bool = true, color: Color = .BrandBlue, action: @escaping () -> Void) {
        self.title = title
        self.busy = busy
        self.enabled = enabled
        self.color = color
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            ZStack {
                if busy { ProgressView().tint(.white) } else { Text(title).font(.system(size: 16, weight: .semibold)) }
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(RoundedRectangle(cornerRadius: 12).fill((enabled && !busy) ? color : color.opacity(0.45)))
        }
        .buttonStyle(.plain)
        .disabled(!enabled || busy)
    }
}

/// Wrapping row layout (Compose FlowRow): `FlowLayout(spacing: 6) { Chip(…); Chip(…) }`.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6
    var lineSpacing: CGFloat = 6

    init(spacing: CGFloat = 6, lineSpacing: CGFloat = 6) {
        self.spacing = spacing
        self.lineSpacing = lineSpacing
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW: CGFloat = proposal.width ?? .greatestFiniteMagnitude
        var x: CGFloat = 0
        var y: CGFloat = 0
        var lineH: CGFloat = 0
        var widest: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > 0 && x + sz.width > maxW {
                x = 0
                y += lineH + lineSpacing
                lineH = 0
            }
            x += sz.width + spacing
            lineH = max(lineH, sz.height)
            widest = max(widest, x - spacing)
        }
        let w: CGFloat = proposal.width ?? widest
        return CGSize(width: w, height: y + lineH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x: CGFloat = bounds.minX
        var y: CGFloat = bounds.minY
        var lineH: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > bounds.minX && x + sz.width > bounds.maxX {
                x = bounds.minX
                y += lineH + lineSpacing
                lineH = 0
            }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(sz))
            x += sz.width + spacing
            lineH = max(lineH, sz.height)
        }
    }
}

/// Bottom toast pill (AppRoot shows `app.toastMessage` with it).
struct ToastBanner: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(.white)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 16).padding(.vertical, 10)
            .background(Capsule().fill(Color.black.opacity(0.82)))
            .padding(.horizontal, 24)
    }
}
