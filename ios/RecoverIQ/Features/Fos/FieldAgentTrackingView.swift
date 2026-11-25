import SwiftUI
import CoreLocation

// Port of ui/fos/FieldAgentScreens.kt → FieldAgentTrackingScreen + FosOnDutyCard.
// The Android battery-optimisation nudge becomes the iOS "Always" location-permission nudge
// (that's what keeps tracking alive with the screen locked on iPhone).

struct FieldAgentTrackingView: View {
    @EnvironmentObject var app: AppState

    init() {}

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                FosOnDutyCard()
                CheckInStatusCard()
                SectionTitle("Today's activity")
                AsyncContent(key: AnyHashable("today-route"), live: true,
                             load: { () async throws -> TodayRoute in try await API.shared.myTodayRoute() }) { route, _ in
                    TodayRouteCard(route: route)
                }
                .frame(minHeight: 80)
            }
            .padding(16)
        }
    }

    @ViewBuilder private var header: some View {
        if let u = app.user {
            VStack(alignment: .leading, spacing: 4) {
                Text("Hello, \(firstName(u.name))")
                    .font(.headlineSmall).fontWeight(.bold).foregroundColor(.TextDark)
                Text(u.roleLabel + (u.branch.map { " · \($0)" } ?? ""))
                    .foregroundColor(.Muted)
            }
        }
    }

    private func firstName(_ name: String) -> String {
        if let sp = name.firstIndex(of: " ") { return String(name[..<sp]) }
        return name
    }
}

// MARK: - Today's route summary

private struct TodayRouteCard: View {
    let route: TodayRoute

    var body: some View {
        InfoCard {
            Text("\(route.count) location updates recorded today")
                .font(.titleMedium).fontWeight(.semibold).foregroundColor(.TextDark)
            if route.distanceKm > 0 {
                Text("Distance covered: \(kmText(route.distanceKm)) km")
                    .font(.bodySmall).foregroundColor(.Muted)
                    .padding(.top, 4)
            }
            if let last = route.points.last {
                Text("Last fix: \(String(format: "%.5f", last.lat)), \(String(format: "%.5f", last.lng))")
                    .font(.bodySmall).foregroundColor(.Muted)
            }
        }
    }
}

/// Kotlin prints the Double as-is ("12.3"); mirror that without trailing noise.
func fosKmText(_ v: Double) -> String {
    let r: Double = (v * 100.0).rounded() / 100.0
    if r == r.rounded() { return String(format: "%.1f", r) }
    return String(r)
}

private func kmText(_ v: Double) -> String { fosKmText(v) }

// MARK: - On duty switch (Kotlin FosOnDutyCard)

/// The on-duty on/off switch (+ "Always" location nudge). Reusable on the FOS home dashboard.
struct FosOnDutyCard: View {
    @ObservedObject private var tracker: LocationTracker = LocationTracker.shared
    @State private var onDuty: Bool = API.shared.onDuty()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switchCard
            if onDuty {
                permissionCard
                trackerStatusCard
            }
        }
        .onAppear {
            onDuty = API.shared.onDuty()
            // If duty was left on (survived a restart), make sure tracking is actually running.
            if onDuty && !tracker.running { tracker.start() }
        }
    }

    private var dutyBinding: Binding<Bool> {
        Binding<Bool>(
            get: { onDuty },
            set: { want in
                onDuty = want
                API.shared.setOnDuty(v: want)
                if want {
                    tracker.requestPermission()
                    tracker.start()
                } else {
                    tracker.stop()
                }
            }
        )
    }

    private var switchCard: some View {
        InfoCard {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(onDuty ? "You're on duty" : "Off duty")
                        .font(.titleMedium).fontWeight(.semibold)
                        .foregroundColor(onDuty ? Color.Good : Color.TextDark)
                    Text(onDuty
                         ? "Live location is shared with your branch, even in the background."
                         : "Turn on to start sharing your live location.")
                        .font(.bodySmall).foregroundColor(.Muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Toggle("", isOn: dutyBinding)
                    .labelsHidden()
                    .tint(.BrandBlue)
            }
        }
    }

    private var permissionText: String {
        switch tracker.permission {
        case "always": return "Location: Always allowed — tracking continues with the screen locked."
        case "when_in_use": return "Location: only While Using the App. Switch to \"Always\" so iOS doesn't pause tracking."
        case "denied": return "Location permission is denied. Turn it on in Settings to share your live location."
        case "restricted": return "Location is restricted on this iPhone."
        case "not_determined": return "Location permission not granted yet."
        default: return "Location permission unknown."
        }
    }

    private var permissionCard: some View {
        InfoCard {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "bolt.fill").foregroundColor(.BrandBlue)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Keep tracking reliable").fontWeight(.semibold).foregroundColor(.TextDark)
                    Text(permissionText)
                        .font(.bodySmall).foregroundColor(.Muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if tracker.permission != "always" {
                HStack(spacing: 12) {
                    if tracker.permission == "not_determined" || tracker.permission == "when_in_use" {
                        Button("Allow \"Always\" location") { tracker.requestPermission() }
                            .font(.labelLarge).foregroundColor(.BrandBlue)
                    }
                    Button("Open Settings") { tracker.openSettings() }
                        .font(.labelLarge).foregroundColor(.BrandBlue)
                }
                .padding(.top, 6)
            }
        }
    }

    private var trackerStatusCard: some View {
        InfoCard {
            HStack(spacing: 8) {
                Circle().fill(tracker.running ? Color.Good : Color.Warn).frame(width: 8, height: 8)
                Text(tracker.running ? "Tracking is running" : "Tracking is not running")
                    .font(.labelLarge).foregroundColor(.TextDark)
                Spacer()
                if !tracker.running {
                    Button("Start") { tracker.start() }
                        .font(.labelLarge).foregroundColor(.BrandBlue)
                }
            }
            if let fix = tracker.lastFix {
                Text("Last GPS: \(String(format: "%.5f", fix.coordinate.latitude)), \(String(format: "%.5f", fix.coordinate.longitude)) · ±\(String(format: "%.0f", fix.horizontalAccuracy)) m")
                    .font(.bodySmall).foregroundColor(.Muted)
            }
            if tracker.lastSentAt > Date.distantPast {
                Text("Last sent: \(sentText(tracker.lastSentAt))")
                    .font(.bodySmall).foregroundColor(.Muted)
            }
            if let err = tracker.lastError, !err.isEmpty {
                Text(err).font(.bodySmall).foregroundColor(.Bad)
            }
        }
    }

    private func sentText(_ d: Date) -> String {
        let f = DateFormatter()
        f.timeZone = DateUtil.ist
        f.dateFormat = "hh:mm:ss a"
        return f.string(from: d)
    }
}

// MARK: - Check-in status (attendance today)

private struct CheckInStatusCard: View {
    @State private var me: MeToday? = nil

    var body: some View {
        Group {
            if let m = me {
                InfoCard {
                    HStack(spacing: 8) {
                        Image(systemName: checkedIn(m) ? "checkmark.circle.fill" : "clock")
                            .foregroundColor(checkedIn(m) ? Color.Good : Color.Warn)
                        Text(title(m)).font(.labelLarge).foregroundColor(.TextDark)
                        Spacer()
                    }
                    if let out = m.attendance.checkOutAt, !out.isEmpty {
                        Text("Checked out: \(DateUtil.humanTime(out))").font(.bodySmall).foregroundColor(.Muted)
                    }
                    Text("Shift \(m.shiftStart) – \(m.shiftEnd)").font(.bodySmall).foregroundColor(.Muted)
                }
            }
        }
        .task { await load() }
        .onReceive(Realtime.shared.changed) { _ in Task { await load() } }
    }

    private func checkedIn(_ m: MeToday) -> Bool {
        if let c = m.attendance.checkInAt, !c.isEmpty { return true }
        return false
    }

    private func title(_ m: MeToday) -> String {
        if let c = m.attendance.checkInAt, !c.isEmpty {
            return "Checked in · \(DateUtil.humanTime(c))" + (m.attendance.late ? " (late)" : "")
        }
        return m.needsCheckin ? "Not checked in yet today" : "No check-in needed"
    }

    private func load() async {
        do {
            let v: MeToday = try await API.shared.attMeToday()
            me = v
        } catch {
            // Status line is informational only — keep whatever we had.
        }
    }
}
