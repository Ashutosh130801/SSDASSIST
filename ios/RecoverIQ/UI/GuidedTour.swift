import SwiftUI

/// One-time, skippable onboarding carousel — port of ui/common/GuidedTour.kt.
/// Bump TOUR_VERSION whenever the app changes enough that everyone should see it again.
let TOUR_VERSION: Int = 1

enum TourPrefs {
    private static func key(_ role: String) -> String { "ssd_tour.seen_\(role)_v\(TOUR_VERSION)" }
    static func seen(_ role: String) -> Bool { UserDefaults.standard.bool(forKey: key(role)) }
    static func markSeen(_ role: String) { UserDefaults.standard.set(true, forKey: key(role)) }
}

/// Plain-language description for each nav destination (mirrors the web tour).
let TOUR_DESC: [String: String] = [
    "dashboard": "Your home base — headline numbers at a glance: cases, recovery %, cash collected, pending and your resolution %.",
    "onduty": "On Duty — turn tracking on when you start the day so your live location is shared with the office.",
    "tldash": "My Team — your team's overview, members and their performance, all scoped to you.",
    "cases": "Accounts — browse your portfolios and open any case for full details, payments and history.",
    "fcases": "My Accounts — your assigned field cases grouped by bank & bucket. Search, filter, or open a case.",
    "queue": "Calling — your call queue: due now, contacted today, upcoming and paid. Search & filter to work faster.",
    "ptp": "PTP Tracker — promise-to-pay cases split into overdue / due today / upcoming so you chase the right ones first.",
    "map": "Field Tracking — live agent locations, routes and visit history.",
    "fmap": "Field Tracking — your live location and today's route; log GPS-stamped visits from a case.",
    "records": "Activity — a live log of every call, visit and payment.",
    "staff": "Team — staff profiles and performance.",
    "templates": "Communication — WhatsApp / SMS message templates.",
    "devices": "Devices — approve or block the devices your staff log in from.",
    "legal": "Litigation — the legal / court case tracker.",
    "leave": "Leave — apply for leave and track approvals.",
    "security": "Security — change your password and set up 2-factor authentication.",
    "profile": "My E-ID — your profile, ID card, personal details and your achievement trends.",
    "myperf": "My Performance — your scorecard per portfolio: achievement %, cash, POS, and the portfolio leaderboard with your rank against peers.",
]

struct TourStep: Hashable {
    let title: String
    let body: String
}

/// Dimmed scrim + centred card with Back / Next / Skip and progress dots.
struct GuidedTour: View {
    let steps: [TourStep]
    let onClose: () -> Void
    @State private var idx: Int = 0

    init(steps: [TourStep], onClose: @escaping () -> Void) {
        self.steps = steps
        self.onClose = onClose
    }

    private var last: Bool { idx >= steps.count - 1 }

    var body: some View {
        ZStack {
            Color.Scrim.ignoresSafeArea()
                .contentShape(Rectangle())
                .onTapGesture {}          // swallow taps on the scrim
            if !steps.isEmpty { card }
        }
    }

    private var card: some View {
        let step = steps[min(idx, steps.count - 1)]
        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center) {
                Text(step.title).font(.system(size: 17, weight: .semibold)).foregroundColor(.TextDark)
                Spacer()
                Button("Skip", action: onClose).foregroundColor(.BrandBlue)
            }
            Text(step.body).font(.bodyMedium).foregroundColor(.Muted).padding(.top, 6)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                HStack(spacing: 4) {
                    ForEach(0..<steps.count, id: \.self) { i in
                        Circle().fill(i == idx ? Color.BrandBlue : Color(argb: 0xFFD1D5DB)).frame(width: 7, height: 7)
                    }
                }
                Spacer()
                if idx > 0 {
                    Button("Back") { idx -= 1 }.foregroundColor(.BrandBlue)
                }
                Button(last ? "Done" : "Next") {
                    if last { onClose() } else { idx += 1 }
                }
                .buttonStyle(.borderedProminent)
                .tint(.BrandBlue)
            }
            .padding(.top, 16)
            Text("Step \(idx + 1) of \(steps.count)").font(.labelSmall).foregroundColor(.Muted).padding(.top, 6)
        }
        .padding(20)
        .frame(maxWidth: 400)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color.CardWhite))
        .shadow(color: Color.black.opacity(0.2), radius: 12, x: 0, y: 4)
        .padding(24)
    }
}
