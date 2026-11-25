import SwiftUI
import UIKit

/// Case details — port of ui/detail/CaseDetailScreen.kt.
/// Header + copy pill, lock banners (closed / escalated), action bar (call / WhatsApp / navigate,
/// call FOS / caller, request callback, payment / log call / visit), personal highlight colours,
/// all detail sections (latest contact, customer + 3 addresses, account, recovery MIS, status),
/// and the activity log (timeline / notes history).
struct CaseDetailView: View {
    let caseId: Int

    @EnvironmentObject var app: AppState

    @State private var caseObj: Case? = nil
    @State private var events: [TimelineEvent]? = nil
    @State private var timelineError: String? = nil
    @State private var loadError: String? = nil
    @State private var refresh: Int = 0

    @State private var showPay: Bool = false
    @State private var showLogCall: Bool = false
    @State private var showVisit: Bool = false
    @State private var showUpi: Bool = false
    @State private var showContactUpdate: Bool = false

    init(caseId: Int) {
        self.caseId = caseId
    }

    var body: some View {
        content
            .navigationTitle("Case details")
            .navigationBarTitleDisplayMode(.inline)
            .appBackground()
            .task(id: refresh) { await load() }
            .onReceive(Realtime.shared.changed) { _ in refresh += 1 }
            .sheet(isPresented: $showPay, onDismiss: { refresh += 1 }) { paySheet }
            .sheet(isPresented: $showLogCall, onDismiss: { refresh += 1 }) { callSheet }
            .sheet(isPresented: $showVisit, onDismiss: { refresh += 1 }) { visitSheet }
            .sheet(isPresented: $showUpi) { upiSheet }
            .sheet(isPresented: $showContactUpdate, onDismiss: { refresh += 1 }) { contactSheet }
    }

    // MARK: - Content

    @ViewBuilder private var content: some View {
        if let c = caseObj, let u = app.user {
            loaded(c, user: u)
        } else if let e = loadError {
            ErrorView(message: e, retry: { refresh += 1 })
        } else {
            LogoLoader().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func loaded(_ c: Case, user u: User) -> some View {
        let frontLine: Bool = u.isFieldAgent || u.isTelecaller
        let closedForMe: Bool = (c.closed == true) && frontLine
        let lockedForMe: Bool = ((c.escalated == true) && frontLine) || closedForMe
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                DetailHeaderCard(c: c)
                    .textSelection(.enabled)
                CopyCaseInfoPill(c: c, onCopy: copy)
                LockBanner(c: c, closedForMe: closedForMe, lockedForMe: lockedForMe)
                if c.jointForMe == true {
                    JointBanner(c: c)
                }
                DetailActionBar(
                    c: c,
                    meId: u.id,
                    canPay: !lockedForMe,
                    canLogCall: !lockedForMe && (u.isTelecaller || u.isAdmin || u.isManager || u.isFieldAgent),
                    canLogVisit: !lockedForMe && u.isFieldAgent,
                    canRequestCallback: u.isFieldAgent && !lockedForMe,
                    canUpdateContact: !lockedForMe && !u.isFieldAgent,
                    hasUpi: (app.upiVpa ?? "").isEmpty == false,
                    onPay: { showPay = true },
                    onLogCall: { showLogCall = true },
                    onLogVisit: { showVisit = true },
                    onUpi: { showUpi = true },
                    onContactUpdate: { showContactUpdate = true }
                )
                HighlightRow(selected: c.reviewColor, onPick: { col in setFlag(col) })
                DetailFieldsView(c: c)
                    .textSelection(.enabled)
                SectionTitle("Activity log")
                timeline
                Spacer().frame(height: 24)
            }
            .padding(16)
        }
        .refreshable { await load() }
    }

    @ViewBuilder private var timeline: some View {
        if let ev = events {
            if ev.isEmpty {
                Text("No activity yet.").foregroundColor(.MutedDim).font(.bodyMedium)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(ev.enumerated()), id: \.offset) { pair in
                        DetailTimelineRow(e: pair.element)
                    }
                }
            }
        } else if let e = timelineError {
            Text(e).foregroundColor(.Bad).font(.bodySmall)
        } else {
            ProgressView().frame(maxWidth: .infinity)
        }
    }

    // MARK: - Sheets

    @ViewBuilder private var paySheet: some View {
        if let c = caseObj { PaymentSheet(case: c, onDone: { showPay = false }) }
    }

    @ViewBuilder private var callSheet: some View {
        if let c = caseObj { LogCallSheet(case: c, onDone: { showLogCall = false }) }
    }

    @ViewBuilder private var visitSheet: some View {
        if let c = caseObj { LogVisitSheet(case: c, onDone: { showVisit = false }) }
    }

    @ViewBuilder private var upiSheet: some View {
        if let c = caseObj {
            DetailUpiSheet(c: c, vpa: app.upiVpa ?? "", payee: app.upiPayeeName, onDone: { showUpi = false })
        }
    }

    @ViewBuilder private var contactSheet: some View {
        if let c = caseObj { DetailContactUpdateSheet(c: c, onDone: { showContactUpdate = false }) }
    }

    // MARK: - Actions

    private func load() async {
        do {
            let c: Case = try await API.shared.getCase(id: caseId)
            caseObj = c
            loadError = nil
        } catch {
            if error is CancellationError { return }
            if caseObj == nil { loadError = error.localizedDescription }
        }
        do {
            let ev: [TimelineEvent] = try await API.shared.timeline(id: caseId)
            events = ev
            timelineError = nil
        } catch {
            if error is CancellationError { return }
            if events == nil { timelineError = error.localizedDescription }
        }
    }

    private func copy(_ text: String, _ msg: String) {
        UIPasteboard.general.string = text
        app.toast(msg)
    }

    private func setFlag(_ color: String?) {
        Task {
            _ = try? await API.shared.setReviewFlag(id: caseId, color: color)
            refresh += 1
        }
    }
}

// MARK: - Small pieces used only by CaseDetailView

/// "📋 Copy case info" pill — tap: key info · double-tap: all details.
private struct CopyCaseInfoPill: View {
    let c: Case
    let onCopy: (String, String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("📋 Copy case info").font(.system(size: 14, weight: .semibold)).foregroundColor(.BrandBlue)
            Text("Tap: key info · Double-tap: all details").font(.labelSmall).foregroundColor(.Muted)
        }
        .padding(.horizontal, 20).padding(.vertical, 8)
        .overlay(Capsule().stroke(Color.BrandBlue.opacity(0.5), lineWidth: 1))
        .contentShape(Capsule())
        .onTapGesture(count: 2) {
            onCopy(CaseText.fullText(c), "ALL case details copied")
        }
        .onTapGesture(count: 1) {
            onCopy(CaseText.infoText(c), "Case info copied · double-tap for ALL details")
        }
    }
}

/// Closed / escalated lock banner for the front-line FOS / caller.
private struct LockBanner: View {
    let c: Case
    let closedForMe: Bool
    let lockedForMe: Bool

    var body: some View {
        if closedForMe {
            Text(closedText)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.TextDark)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.Muted.opacity(0.15)))
        } else if lockedForMe {
            Text("🚩 Escalated — locked. Your team lead / manager is handling this case.")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.Bad)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.Bad.opacity(0.12)))
        }
    }

    private var closedText: String {
        var s: String = "🔒 Case closed"
        if let d = c.closeDate { s += " on " + d }
        s += " — locked. No visits, calls, payments or changes. You can still view it."
        return s
    }
}

/// Joint allocation notice (this FOS is the joint FOS on someone else's case).
private struct JointBanner: View {
    let c: Case

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("🤝 Joint allocation — you are the joint FOS on this case")
                .font(.system(size: 12, weight: .semibold))
            if let n = CaseText.nb(c.jointNote) {
                Text(n).font(.bodySmall).foregroundColor(.Muted)
            }
        }
        .foregroundColor(.BrandBlueDark)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.BrandBlue.opacity(0.10)))
    }
}

/// "🔖 Highlight:" personal colour dots + Clear.
private struct HighlightRow: View {
    let selected: String?
    let onPick: (String?) -> Void

    var body: some View {
        HStack(spacing: 8) {
            Text("🔖 Highlight:").font(.labelMedium).foregroundColor(.Muted)
            ForEach(REVIEW_COLOR_NAMES, id: \.self) { col in
                dot(col)
            }
            if CaseText.nb(selected) != nil {
                Button("Clear") { onPick(nil) }
                    .font(.labelMedium)
            }
            Spacer(minLength: 0)
        }
    }

    private func dot(_ col: String) -> some View {
        let isSel: Bool = selected == col
        let fill: Color = reviewColorOf(col) ?? Color.MutedDim
        return Circle()
            .fill(fill)
            .frame(width: 24, height: 24)
            .overlay(Circle().stroke(isSel ? Color.TextDark : Color.GlassStroke, lineWidth: isSel ? 3 : 1))
            .contentShape(Circle())
            .onTapGesture { onPick(isSel ? nil : col) }
    }
}
