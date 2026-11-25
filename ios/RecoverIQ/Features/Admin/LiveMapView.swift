import SwiftUI
import MapKit
import UIKit

// Port of AdminScreens.kt LiveMapScreen + OsmLiveMap.kt / GoogleMapKit.kt GoogleLiveMap:
//  * officer list first, compact live map underneath (polls /api/tracking/live every 4 s),
//  * each agent is one persistent green "live rider" dot that GLIDES to its new fix (MapKitView diffs by id)
//    and trails a breadcrumb line as it moves; agents that leave the feed are dropped,
//  * "History" opens a big map with the agent's day route (blue line + heading arrows, S/E pins),
//    a date picker and a replay scrubber that walks a marker along the recorded points.

private let LIVE_GREEN: UIColor = UIColor(red: 0x16 / 255.0, green: 0xA3 / 255.0, blue: 0x4A / 255.0, alpha: 1)
private let ROUTE_BLUE: UIColor = UIColor(red: 0x25 / 255.0, green: 0x63 / 255.0, blue: 0xEB / 255.0, alpha: 1)
private let END_RED: UIColor = UIColor(red: 0xDC / 255.0, green: 0x26 / 255.0, blue: 0x26 / 255.0, alpha: 1)

struct LiveMapView: View {
    @State private var officers: [OfficerLocation] = []
    @State private var trails: [Int: [CLLocationCoordinate2D]] = [:]
    @State private var expanded: Bool = false
    @State private var selected: OfficerLocation? = nil
    @State private var route: [PingOut] = []
    @State private var loadingRoute: Bool = false
    @State private var routeDate: String = DateUtil.todayIso()
    @State private var replayIdx: Int = 0
    @State private var replaying: Bool = false
    @State private var playing: Bool = false

    init() {}

    var body: some View {
        ZStack {
            if expanded {
                expandedView
            } else {
                listView
            }
        }
        .task { await pollLoop() }
    }

    // MARK: data

    private func pollLoop() async {
        while !Task.isCancelled {
            if let list = try? await API.shared.liveOfficers() {
                applyOfficers(list)
            }
            try? await Task.sleep(nanoseconds: 4_000_000_000)
        }
    }

    /// Extend each agent's breadcrumb when it moved; drop agents that left the live feed.
    private func applyOfficers(_ list: [OfficerLocation]) {
        var next: [Int: [CLLocationCoordinate2D]] = [:]
        for o in list {
            let to = CLLocationCoordinate2D(latitude: o.latitude, longitude: o.longitude)
            var pts: [CLLocationCoordinate2D] = trails[o.officerId] ?? []
            if let last = pts.last {
                if last.latitude != to.latitude || last.longitude != to.longitude { pts.append(to) }
            } else {
                pts.append(to)
            }
            if pts.count > 500 { pts.removeFirst(pts.count - 500) }
            next[o.officerId] = pts
        }
        trails = next
        officers = list
    }

    private func openHistory(_ o: OfficerLocation) {
        selected = o
        expanded = true
        routeDate = DateUtil.todayIso()
        Task { await loadRoute() }
    }

    private func loadRoute() async {
        guard let o = selected else { return }
        route = []
        replaying = false
        playing = false
        replayIdx = 0
        loadingRoute = true
        let today: String = DateUtil.todayIso()
        let date: String? = routeDate == today ? nil : routeDate
        let pts: [PingOut] = (try? await API.shared.officerRoute(officerId: o.officerId, date: date)) ?? []
        route = pts
        loadingRoute = false
    }

    private func closeHistory() {
        expanded = false
        playing = false
        replaying = false
        route = []
    }

    // MARK: default — list + compact map

    private var listView: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Field agents — live")
                .padding(.horizontal, 16)
                .padding(.top, 4)
            ScrollView {
                LazyVStack(spacing: 8) {
                    if officers.isEmpty {
                        Text("No field agents have shared a location today. They appear here once their app sends a position.")
                            .font(.bodyMedium)
                            .foregroundColor(.Muted)
                            .padding(12)
                    }
                    ForEach(officers, id: \.officerId) { o in
                        OfficerRow(o: o, onHistory: { openHistory(o) })
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
            }
            .frame(maxHeight: .infinity)
            SectionTitle("Live map")
                .padding(.horizontal, 16)
            MapKitView(markers: liveMarkers(), lines: trailLines())
                .frame(height: 280)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
        }
    }

    // MARK: expanded — route history

    private var routeCoords: [CLLocationCoordinate2D] {
        route.map { CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude) }
    }

    private var routeStatus: String {
        if loadingRoute { return "Loading route…" }
        if route.isEmpty { return routeDate == DateUtil.todayIso() ? "No route recorded today" : "No route recorded on this day" }
        let km: Double = LiveMapMath.distanceKm(routeCoords)
        return "\(route.count) points · \(String(format: "%.1f", km)) km · 🟢 S start · 🔴 E end"
    }

    private var expandedView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button(action: { closeHistory() }) {
                    Text("‹ Back to list").font(.labelLarge).foregroundColor(.BrandBlue)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(selected?.name ?? "Route").fontWeight(.bold).foregroundColor(.TextDark).lineLimit(1)
                    Text(routeStatus).font(.bodySmall).foregroundColor(.Muted).lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            HStack {
                DatePickerField(label: "Date", iso: routeDate, maxDate: Date(), onPick: { d in
                    routeDate = d
                    Task { await loadRoute() }
                })
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 6)
            ZStack(alignment: .bottom) {
                MapKitView(markers: expandedMarkers(), lines: expandedLines(),
                           fitKey: AnyHashable("route|\(selected?.officerId ?? 0)|\(routeDate)|\(route.count)"))
                if route.count >= 2 {
                    ReplayBar(count: route.count, index: $replayIdx, replaying: $replaying, playing: $playing,
                              timeLabel: replayTimeLabel)
                        .padding(10)
                }
            }
        }
        .task(id: playing) { await playLoop() }
    }

    private var replayTimeLabel: String {
        guard replayIdx >= 0, replayIdx < route.count else { return "" }
        return DateUtil.humanTime(route[replayIdx].createdAt)
    }

    /// Walks the replay marker along the route while `playing` (~ 20 s for the whole day, min 60 ms/step).
    private func playLoop() async {
        guard playing else { return }
        replaying = true
        if replayIdx >= route.count - 1 { replayIdx = 0 }
        let n: Int = max(route.count, 1)
        let stepNs: UInt64 = UInt64(max(60_000_000, 20_000_000_000 / n))
        while playing && !Task.isCancelled && replayIdx < route.count - 1 {
            try? await Task.sleep(nanoseconds: stepNs)
            if Task.isCancelled { return }
            replayIdx += 1
        }
        playing = false
    }

    // MARK: map content

    private func liveMarkers() -> [RIQMapMarker] {
        return officers.map { o in
            RIQMapMarker(id: "live#\(o.officerId)", latitude: o.latitude, longitude: o.longitude,
                         title: o.name, subtitle: "Last seen: " + DateUtil.humanTime(o.lastSeen),
                         color: LIVE_GREEN, style: .liveDot)
        }
    }

    private func trailLines() -> [RIQMapLine] {
        var out: [RIQMapLine] = []
        for (id, pts) in trails where pts.count >= 2 {
            out.append(RIQMapLine(id: "trail#\(id)", coordinates: pts, color: LIVE_GREEN.withAlphaComponent(0.6), width: 4))
        }
        return out
    }

    /// With a route on screen only the selected agent's live pin/trail is kept, so the map fits the route.
    private var focusOnRoute: Bool { route.count >= 2 }

    private func expandedMarkers() -> [RIQMapMarker] {
        let sid: Int = selected?.officerId ?? -1
        var out: [RIQMapMarker] = liveMarkers().filter { m in !focusOnRoute || m.id == "live#\(sid)" }
        let pts: [CLLocationCoordinate2D] = routeCoords
        if pts.count >= 2, let s = pts.first, let e = pts.last {
            out.append(RIQMapMarker(id: "route#start", latitude: s.latitude, longitude: s.longitude,
                                    title: "S · Start", subtitle: DateUtil.humanTime(route.first?.createdAt),
                                    color: LIVE_GREEN, style: .liveDot))
            out.append(RIQMapMarker(id: "route#end", latitude: e.latitude, longitude: e.longitude,
                                    title: "E · End", subtitle: DateUtil.humanTime(route.last?.createdAt),
                                    color: END_RED, style: .dot))
            if replaying, replayIdx >= 0, replayIdx < pts.count {
                let p = pts[replayIdx]
                out.append(RIQMapMarker(id: "route#replay", latitude: p.latitude, longitude: p.longitude,
                                        title: selected?.name ?? "Replay", subtitle: replayTimeLabel,
                                        color: ROUTE_BLUE, style: .liveDot))
            }
        }
        return out
    }

    private func expandedLines() -> [RIQMapLine] {
        let sid: Int = selected?.officerId ?? -1
        var out: [RIQMapLine] = trailLines().filter { l in !focusOnRoute || l.id == "trail#\(sid)" }
        let pts: [CLLocationCoordinate2D] = routeCoords
        if pts.count >= 2 {
            out.append(RIQMapLine(id: "route", coordinates: pts, color: ROUTE_BLUE, width: 6, arrows: true))
        }
        return out
    }
}

// MARK: - Subviews

private struct OfficerRow: View {
    let o: OfficerLocation
    let onHistory: () -> Void

    var body: some View {
        InfoCard {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("● \(o.name)").fontWeight(.semibold).foregroundColor(.BrandBlue)
                    Text("Last seen: \(DateUtil.humanTime(o.lastSeen))")
                        .font(.bodySmall).foregroundColor(.Muted)
                }
                Spacer()
                Button(action: onHistory) {
                    Text("🕘 History")
                        .font(.labelLarge)
                        .foregroundColor(.BrandBlue)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .overlay(Capsule().stroke(Color.BrandBlue.opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// Play / pause + scrubber for the route replay.
private struct ReplayBar: View {
    let count: Int
    @Binding var index: Int
    @Binding var replaying: Bool
    @Binding var playing: Bool
    let timeLabel: String

    private var sliderValue: Binding<Double> {
        Binding<Double>(get: { Double(index) },
                        set: { v in
                            replaying = true
                            playing = false
                            index = min(max(Int(v.rounded()), 0), max(count - 1, 0))
                        })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 10) {
                Button(action: {
                    if playing { playing = false } else { replaying = true; playing = true }
                }) {
                    Image(systemName: playing ? "pause.fill" : "play.fill")
                        .foregroundColor(.white)
                        .frame(width: 34, height: 34)
                        .background(Circle().fill(Color.BrandBlue))
                }
                .buttonStyle(.plain)
                Slider(value: sliderValue, in: 0...Double(max(count - 1, 1)), step: 1)
                    .tint(.BrandBlue)
                if replaying {
                    Button(action: { playing = false; replaying = false; index = 0 }) {
                        Image(systemName: "xmark.circle.fill").foregroundColor(.MutedDim)
                    }
                    .buttonStyle(.plain)
                }
            }
            Text(replaying ? "Replay · \(index + 1)/\(count) · \(timeLabel)" : "Replay the route")
                .font(.labelSmall)
                .foregroundColor(.Muted)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite.opacity(0.95)))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.GlassStroke, lineWidth: 1))
        .shadow(color: Color.black.opacity(0.1), radius: 6, x: 0, y: 2)
    }
}

enum LiveMapMath {
    /// Haversine path length in km.
    static func distanceKm(_ pts: [CLLocationCoordinate2D]) -> Double {
        if pts.count < 2 { return 0 }
        var total: Double = 0
        for i in 1..<pts.count {
            let a = CLLocation(latitude: pts[i - 1].latitude, longitude: pts[i - 1].longitude)
            let b = CLLocation(latitude: pts[i].latitude, longitude: pts[i].longitude)
            total += a.distance(from: b)
        }
        return total / 1000.0
    }
}
