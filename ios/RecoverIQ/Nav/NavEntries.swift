import SwiftUI

/// One side-menu destination (Kotlin NavEntry). `icon` is an SF Symbol name.
struct NavEntry: Identifiable, Hashable {
    let key: String
    let label: String
    let icon: String
    var id: String { key }
}

/// Role → menu entries, identical order/labels/conditions to AppRoot.kt navEntriesFor()
/// (+ "Attendance" and the payslips-service-gated "My Payslips" appended for everyone).
enum NavCatalog {
    static func entries(for user: User, payslipsOn: Bool) -> [NavEntry] {
        var items = roleEntries(user)
        items.append(NavEntry(key: "attendance", label: "Attendance", icon: "clock.fill"))
        if payslipsOn { items.append(NavEntry(key: "payslips", label: "My Payslips", icon: "doc.text.fill")) }
        return items
    }

    static func roleEntries(_ user: User) -> [NavEntry] {
        let dashboard = NavEntry(key: "dashboard", label: (user.isFieldAgent || user.isTelecaller) ? "My Stats" : "Dashboard",
                                 icon: "square.grid.2x2.fill")
        let profile = NavEntry(key: "profile", label: "My E-ID", icon: "person.text.rectangle.fill")
        let leave = NavEntry(key: "leave", label: "Leave", icon: "beach.umbrella.fill")
        let security = NavEntry(key: "security", label: "Security", icon: "lock.fill")
        let changeReqs = NavEntry(key: "preqs", label: "Change Requests", icon: "person.text.rectangle")
        let mis = NavEntry(key: "mis", label: "MIS", icon: "chart.bar.doc.horizontal.fill")
        let todo = NavEntry(key: "todo", label: "My Work Queue", icon: "checklist")
        let rtsb = NavEntry(key: "rtsb", label: "RTSB", icon: "trophy.fill")
        let monitor = NavEntry(key: "monitor", label: "Live Monitor", icon: "clock.arrow.circlepath")
        let ptp = NavEntry(key: "ptp", label: "PTP Tracker", icon: "hand.thumbsup.fill")
        let legal = NavEntry(key: "legal", label: "Litigation", icon: "building.columns.fill")
        let map = NavEntry(key: "map", label: "Field Tracking", icon: "map.fill")
        let staff = NavEntry(key: "staff", label: "Team", icon: "person.3.fill")
        let templates = NavEntry(key: "templates", label: "Communication", icon: "phone.bubble.left.fill")
        let devices = NavEntry(key: "devices", label: "Devices", icon: "iphone")
        let myperf = NavEntry(key: "myperf", label: "My Performance", icon: "trophy.fill")

        switch user.role {
        case "fos":
            return [
                NavEntry(key: "dashboard", label: "My Stats", icon: "square.grid.2x2.fill"),
                NavEntry(key: "onduty", label: "On Duty", icon: "location.fill"),
                NavEntry(key: "fcases", label: "My Accounts", icon: "doc.text.fill"),
                NavEntry(key: "myvisits", label: "Today's Visits", icon: "checkmark.rectangle.stack.fill"),
                NavEntry(key: "jointcases", label: "Joint Cases", icon: "person.2.fill"),
                NavEntry(key: "fmap", label: "Field Tracking", icon: "map.fill"),
                myperf, todo, profile, leave, security,
            ]
        case "telecaller":
            return [
                dashboard,
                NavEntry(key: "queue", label: "Calling", icon: "phone.fill"),
                ptp, myperf, todo, profile, leave, security,
            ]
        case "teamlead":
            return [
                NavEntry(key: "tldash", label: "My Team", icon: "person.3.fill"),
                NavEntry(key: "cases", label: "Team Accounts", icon: "doc.text.fill"),
                ptp, mis, rtsb, monitor, todo, profile, leave, security,
            ]
        case "manager":
            return [
                dashboard,
                NavEntry(key: "cases", label: "Accounts", icon: "doc.text.fill"),
                mis, rtsb, monitor, todo, ptp, legal, map, staff, profile, leave, templates, devices, security,
            ]
        case "hr":
            // HR: identity card + leave + change-request review + security (no case portfolios).
            return [profile, changeReqs, leave, security]
        case "it", "staff":
            return [profile, leave, security]
        default:
            // admin + head office + backend + support views
            var out: [NavEntry] = [
                dashboard,
                NavEntry(key: "cases", label: "Accounts", icon: "doc.text.fill"),
                mis, rtsb, monitor, todo, ptp, legal, map,
                NavEntry(key: "records", label: "Activity", icon: "clock.arrow.circlepath"),
                staff,
            ]
            if user.isAdmin { out.append(changeReqs) }   // approvers are admin + HR only
            out.append(contentsOf: [profile, leave, templates, devices, security])
            return out
        }
    }

    /// Guided-tour steps for the menu (welcome + one per entry + done).
    static func tourSteps(user: User, items: [NavEntry]) -> [TourStep] {
        let first = String(user.name.split(separator: " ").first ?? Substring(user.name))
        var steps: [TourStep] = [TourStep(title: "👋 Welcome, \(first)!",
            body: "A quick tour of your \(user.roleLabel) workspace — we'll walk through each feature. Skip anytime and reopen it from the \"?\" button at the bottom-right.")]
        for it in items {
            steps.append(TourStep(title: it.label, body: TOUR_DESC[it.key] ?? "Open \(it.label)."))
        }
        steps.append(TourStep(title: "🎉 You're all set!", body: "That's the tour. Tap the \"?\" button anytime to see it again. Happy working!"))
        return steps
    }
}

/// The screen for a menu key. Every view here is owned by a Features/<Group>/ file.
struct NavScreen: View {
    let key: String
    let onOpenCase: (Int) -> Void

    var body: some View { screen() }

    // AnyView per case keeps the type-checker fast (a 28-way ViewBuilder switch nests deeply).
    private func screen() -> AnyView {
        let open = onOpenCase
        switch key {
        case "dashboard": return AnyView(DashboardView())
        case "onduty": return AnyView(FieldAgentTrackingView())
        case "fcases": return AnyView(MyCasesView(onOpenCase: open))
        case "myvisits": return AnyView(MyVisitsView(onOpenCase: open))
        case "jointcases": return AnyView(JointCasesView(onOpenCase: open))
        case "fmap": return AnyView(FieldTrackingView())
        case "myperf": return AnyView(MyPerformanceView())
        case "queue": return AnyView(CallQueueView(onOpenCase: open))
        case "ptp": return AnyView(PtpTrackerView(onOpenCase: open))
        case "tldash": return AnyView(TeamLeadDashboardView(onOpenCase: open))
        case "cases": return AnyView(PortfolioView(onOpenCase: open))
        case "mis": return AnyView(MisView())
        case "rtsb": return AnyView(RtsbView())
        case "monitor": return AnyView(MonitorView())
        case "todo": return AnyView(TodoView(onOpenCase: open))
        case "legal": return AnyView(LitigationView())
        case "map": return AnyView(LiveMapView())
        case "records": return AnyView(ActivityView())
        case "staff": return AnyView(TeamView())
        case "templates": return AnyView(CommunicationView())
        case "devices": return AnyView(DevicesView())
        case "profile": return AnyView(ProfileView())
        case "leave": return AnyView(LeaveView())
        case "security": return AnyView(SecurityView())
        case "preqs": return AnyView(ChangeRequestsView())
        case "attendance": return AnyView(AttendanceView())
        case "payslips": return AnyView(PayslipsView())
        default: return AnyView(EmptyState(text: "Not available"))
        }
    }
}
