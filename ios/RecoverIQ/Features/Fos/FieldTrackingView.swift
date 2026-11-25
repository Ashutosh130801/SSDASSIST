import SwiftUI
import UIKit
import CoreLocation

// Port of ui/fos/FieldTrackingScreen.kt — my route today (live, re-pulled every 4 s so the "You" pin
// glides) plus my allocated cases pinned on the map (tap a pin's ⓘ to navigate there).

struct FieldTrackingView: View {
    init() {}

    @State private var route: TodayRoute? = nil
    @State private var cases: [Case] = []

    private var located: Int {
        cases.filter { $0.latitude != nil && $0.longitude != nil }.count
    }

    var body: some View {
        // Plain column (no ScrollView) so map pan/zoom gestures don't fight a scroll view.
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                SectionTitle("My route + allocated cases")
                    .padding(.top, 12).padding(.leading, 4)
                stats.padding(.top, 4)
                FieldRouteMap(points: route?.points ?? [], cases: cases)
                    .frame(height: 440)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding(.top, 10)
                if !cases.isEmpty && located == 0 {
                    Text("No case locations yet — an admin needs to run \"Geocode addresses\" so your cases pin on the map.")
                        .font(.labelSmall).foregroundColor(.Muted)
                        .padding(.top, 6).padding(.leading, 4)
                }
            }
            .padding(.horizontal, 12)
            Spacer(minLength: 0)
        }
        .task { await loadCases() }
        .task { await pollRoute() }
    }

    private var stats: some View {
        HStack(spacing: 10) {
            FieldStatCard(value: "\(route?.count ?? 0)", label: "GPS points")
            FieldStatCard(value: "\(fosKmText(route?.distanceKm ?? 0.0)) km", label: "Distance")
            FieldStatCard(value: "\(located)", label: "Cases on map")
        }
    }

    /// My allocated cases (loaded once).
    private func loadCases() async {
        do {
            let v: [Case] = try await API.shared.myCases()
            cases = v
        } catch {
            cases = []
        }
    }

    /// Live refresh: re-pull my route every few seconds so the pin moves as I do.
    private func pollRoute() async {
        while !Task.isCancelled {
            do {
                let r: TodayRoute = try await API.shared.myTodayRoute()
                route = r
            } catch {
                if error is CancellationError { return }
                // keep the previous route
            }
            do {
                try await Task.sleep(nanoseconds: 4_000_000_000)
            } catch {
                return
            }
        }
    }
}

private struct FieldStatCard: View {
    let value: String
    let label: String

    var body: some View {
        InfoCard {
            Text(value).font(.titleLarge).fontWeight(.bold).foregroundColor(.BrandBlue)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(label).font(.labelSmall).foregroundColor(.Muted)
        }
    }
}

private struct FieldRouteMap: View {
    let points: [RoutePoint]
    let cases: [Case]

    private var lineColor: UIColor { UIColor(Color.BrandBlue) }

    private var coords: [CLLocationCoordinate2D] {
        points.map { CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lng) }
    }

    private var caseMarkers: [RIQMapMarker] {
        var out: [RIQMapMarker] = []
        for c in cases {
            guard let lat = c.latitude, let lng = c.longitude else { continue }
            let approx: Bool = c.locationSource != "field" && (c.geoPrecision == "pincode" || c.geoPrecision == "city")
            let title: String = (c.customerName ?? "Case #\(c.id)") + (approx ? "  (approx)" : "")
            var parts: [String] = []
            if let b = c.bank { parts.append(b) }
            parts.append("Pending ₹\(Int(c.pendingAmount))")
            parts.append("Tap to navigate")
            out.append(RIQMapMarker(id: "case-\(c.id)", latitude: lat, longitude: lng, title: title,
                                    subtitle: parts.joined(separator: " · "), style: .pin, tag: c.id))
        }
        return out
    }

    private var routeMarkers: [RIQMapMarker] {
        guard let first = points.first, let last = points.last else { return [] }
        let start = RIQMapMarker(id: "start", latitude: first.lat, longitude: first.lng, title: "Start",
                                 color: UIColor.systemGreen, style: .dot)
        let you = RIQMapMarker(id: "you", latitude: last.lat, longitude: last.lng, title: "You",
                               color: lineColor, style: .liveDot)
        return [start, you]
    }

    private var lines: [RIQMapLine] {
        if coords.isEmpty { return [] }
        return [RIQMapLine(id: "route", coordinates: coords, color: lineColor, width: 4, arrows: true)]
    }

    private var center: CLLocationCoordinate2D? {
        guard let last = points.last else { return nil }
        return CLLocationCoordinate2D(latitude: last.lat, longitude: last.lng)
    }

    var body: some View {
        MapKitView(markers: caseMarkers + routeMarkers,
                   lines: lines,
                   showsUserLocation: false,
                   fitKey: nil,
                   centerOn: center,
                   centerZoomMeters: 4000,
                   onMarkerTap: { m in navigate(m) })
    }

    private func navigate(_ m: RIQMapMarker) {
        guard let id = m.tag, let c = cases.first(where: { $0.id == id }) else { return }
        Actions.navigate(lat: c.latitude, lng: c.longitude, address: c.customerName)
    }
}
