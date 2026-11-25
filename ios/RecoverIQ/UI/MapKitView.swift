import SwiftUI
import UIKit
import MapKit

// MKMapView wrapper replacing OsmLiveMap.kt / GoogleMapKit.kt / MapKit.kt (osmdroid helpers).
//
//   MapKitView(markers: [RIQMapMarker], lines: [RIQMapLine],
//              showsUserLocation: true, fitKey: someHashable, centerOn: coord, onMarkerTap: { m in … })
//
//  * Markers are diffed by `id`: an existing marker whose coordinate changes GLIDES to the new spot
//    (Swiggy-style live rider, Kotlin animateMarker/glide).
//  * Styles: .pin (balloon, tinted), .dot (solid dot + white ring), .liveDot (dot + soft halo),
//    .arrow(bearing:) (heading arrow).
//  * Lines: polylines with colour/width/dash; `arrows: true` sprinkles ~14 heading arrows along the route
//    (Kotlin addDirectionArrows) so you can see which way the agent went.
//  * Fit-to-content: on the first non-empty content, and again whenever `fitKey` changes.
//  * `centerOn`: re-centres (animated) whenever this coordinate changes (follow the "You" pin).
//  * `onMarkerTap`: called when the callout's ⓘ button of a marker with a `tag` is tapped (e.g. navigate to case).
// Names are RIQ-prefixed because MapKit already defines SwiftUI `MapMarker` / `MapPin`.

struct RIQMapMarker: Identifiable, Equatable {
    enum Style: Equatable {
        case pin
        case dot
        case liveDot
        case arrow(bearing: Double)
    }

    var id: String
    var latitude: Double
    var longitude: Double
    var title: String? = nil
    var subtitle: String? = nil
    var color: UIColor = UIColor(red: 0.86, green: 0.15, blue: 0.15, alpha: 1)
    var style: Style = .pin
    var alpha: CGFloat = 1
    /// Free-form tag (e.g. case id) handed back in onMarkerTap.
    var tag: Int? = nil

    init(id: String, latitude: Double, longitude: Double, title: String? = nil, subtitle: String? = nil,
         color: UIColor = UIColor(red: 0.86, green: 0.15, blue: 0.15, alpha: 1), style: Style = .pin,
         alpha: CGFloat = 1, tag: Int? = nil) {
        self.id = id
        self.latitude = latitude
        self.longitude = longitude
        self.title = title
        self.subtitle = subtitle
        self.color = color
        self.style = style
        self.alpha = alpha
        self.tag = tag
    }

    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: latitude, longitude: longitude) }
}

struct RIQMapLine: Identifiable, Equatable {
    var id: String
    var coordinates: [CLLocationCoordinate2D]
    var color: UIColor = UIColor(red: 0.15, green: 0.39, blue: 0.92, alpha: 1)
    var width: CGFloat = 5
    var arrows: Bool = false
    var dashed: Bool = false

    init(id: String, coordinates: [CLLocationCoordinate2D], color: UIColor = UIColor(red: 0.15, green: 0.39, blue: 0.92, alpha: 1),
         width: CGFloat = 5, arrows: Bool = false, dashed: Bool = false) {
        self.id = id
        self.coordinates = coordinates
        self.color = color
        self.width = width
        self.arrows = arrows
        self.dashed = dashed
    }

    /// Convenience from (lat, lng) pairs.
    init(id: String, points: [(Double, Double)], color: UIColor = UIColor(red: 0.15, green: 0.39, blue: 0.92, alpha: 1),
         width: CGFloat = 5, arrows: Bool = false, dashed: Bool = false) {
        self.init(id: id, coordinates: points.map { CLLocationCoordinate2D(latitude: $0.0, longitude: $0.1) },
                  color: color, width: width, arrows: arrows, dashed: dashed)
    }

    /// Cheap change signature (count + endpoints + style).
    var signature: String {
        guard let f = coordinates.first, let l = coordinates.last else { return id + ":0" }
        return "\(id):\(coordinates.count):\(f.latitude),\(f.longitude):\(l.latitude),\(l.longitude):\(width):\(arrows):\(dashed):\(color.description)"
    }

    static func == (a: RIQMapLine, b: RIQMapLine) -> Bool { a.signature == b.signature }
}

/// Compass bearing in degrees (0 = north, clockwise) from a to b (Kotlin bearingDeg).
func bearingDeg(_ a: CLLocationCoordinate2D, _ b: CLLocationCoordinate2D) -> Double {
    let lat1 = a.latitude * .pi / 180
    let lat2 = b.latitude * .pi / 180
    let dLon = (b.longitude - a.longitude) * .pi / 180
    let y = sin(dLon) * cos(lat2)
    let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dLon)
    let deg = atan2(y, x) * 180 / .pi
    return (deg + 360).truncatingRemainder(dividingBy: 360)
}

final class RIQAnnotation: NSObject, MKAnnotation {
    @objc dynamic var coordinate: CLLocationCoordinate2D
    var title: String?
    var subtitle: String?
    var marker: RIQMapMarker

    init(_ m: RIQMapMarker) {
        marker = m
        coordinate = m.coordinate
        title = m.title
        subtitle = m.subtitle
        super.init()
    }
}

final class RIQPolyline: MKPolyline {
    var color: UIColor = .systemBlue
    var width: CGFloat = 5
    var dashed: Bool = false
    var lineId: String = ""
}

struct MapKitView: UIViewRepresentable {
    var markers: [RIQMapMarker] = []
    var lines: [RIQMapLine] = []
    var showsUserLocation: Bool = false
    var fitKey: AnyHashable? = nil
    var centerOn: CLLocationCoordinate2D? = nil
    var centerZoomMeters: Double = 1500
    var onMarkerTap: ((RIQMapMarker) -> Void)? = nil

    init(markers: [RIQMapMarker] = [], lines: [RIQMapLine] = [], showsUserLocation: Bool = false,
         fitKey: AnyHashable? = nil, centerOn: CLLocationCoordinate2D? = nil, centerZoomMeters: Double = 1500,
         onMarkerTap: ((RIQMapMarker) -> Void)? = nil) {
        self.markers = markers
        self.lines = lines
        self.showsUserLocation = showsUserLocation
        self.fitKey = fitKey
        self.centerOn = centerOn
        self.centerZoomMeters = centerZoomMeters
        self.onMarkerTap = onMarkerTap
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView(frame: .zero)
        map.delegate = context.coordinator
        map.showsCompass = true
        map.showsScale = true
        map.pointOfInterestFilter = .excludingAll
        let india = CLLocationCoordinate2D(latitude: 20.5937, longitude: 78.9629)
        map.setRegion(MKCoordinateRegion(center: india, span: MKCoordinateSpan(latitudeDelta: 25, longitudeDelta: 25)), animated: false)
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        let c = context.coordinator
        c.parent = self
        if map.showsUserLocation != showsUserLocation { map.showsUserLocation = showsUserLocation }
        c.syncLines(map, lines)
        c.syncMarkers(map, markers)
        c.handleFit(map)
        c.handleCenter(map)
    }

    // MARK: - Coordinator

    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: MapKitView
        private var annotations: [String: RIQAnnotation] = [:]
        private var arrowAnnotations: [String: [RIQAnnotation]] = [:]
        private var polylines: [String: RIQPolyline] = [:]
        private var lineSigs: [String: String] = [:]
        private var fitted = false
        private var lastFitKey: AnyHashable? = nil
        private var lastCenter: CLLocationCoordinate2D? = nil

        init(_ parent: MapKitView) { self.parent = parent }

        // Lines + their direction arrows
        func syncLines(_ map: MKMapView, _ lines: [RIQMapLine]) {
            let wanted = Set(lines.map { $0.id })
            for (id, pl) in polylines where !wanted.contains(id) {
                map.removeOverlay(pl)
                polylines[id] = nil
                lineSigs[id] = nil
                if let arrows = arrowAnnotations[id] { map.removeAnnotations(arrows) }
                arrowAnnotations[id] = nil
            }
            for line in lines {
                let sig = line.signature
                if lineSigs[line.id] == sig { continue }
                if let old = polylines[line.id] { map.removeOverlay(old) }
                if let arrows = arrowAnnotations[line.id] { map.removeAnnotations(arrows) }
                arrowAnnotations[line.id] = nil
                lineSigs[line.id] = sig
                guard line.coordinates.count >= 2 else { polylines[line.id] = nil; continue }
                var coords = line.coordinates
                let pl = RIQPolyline(coordinates: &coords, count: coords.count)
                pl.color = line.color
                pl.width = line.width
                pl.dashed = line.dashed
                pl.lineId = line.id
                polylines[line.id] = pl
                map.addOverlay(pl, level: .aboveRoads)
                if line.arrows {
                    let arrows = makeArrows(line)
                    arrowAnnotations[line.id] = arrows
                    map.addAnnotations(arrows)
                }
            }
        }

        private func makeArrows(_ line: RIQMapLine, count: Int = 14) -> [RIQAnnotation] {
            let pts = line.coordinates
            var out: [RIQAnnotation] = []
            if pts.count < 2 { return out }
            let step = max(1, pts.count / count)
            var i = step
            while i < pts.count {
                let a = pts[i - 1]
                let b = pts[i]
                if a.latitude != b.latitude || a.longitude != b.longitude {
                    let m = RIQMapMarker(id: line.id + "#arrow#\(i)", latitude: b.latitude, longitude: b.longitude,
                                         color: line.color, style: .arrow(bearing: bearingDeg(a, b)))
                    out.append(RIQAnnotation(m))
                }
                i += step
            }
            return out
        }

        // Markers (diffed by id; moved ones glide)
        func syncMarkers(_ map: MKMapView, _ markers: [RIQMapMarker]) {
            let wanted = Set(markers.map { $0.id })
            for (id, ann) in annotations where !wanted.contains(id) {
                map.removeAnnotation(ann)
                annotations[id] = nil
            }
            for m in markers {
                if let ann = annotations[m.id] {
                    let old = ann.marker
                    if old.style != m.style || old.color != m.color || old.alpha != m.alpha {
                        map.removeAnnotation(ann)
                        let fresh = RIQAnnotation(m)
                        annotations[m.id] = fresh
                        map.addAnnotation(fresh)
                        continue
                    }
                    ann.marker = m
                    ann.title = m.title
                    ann.subtitle = m.subtitle
                    if old.latitude != m.latitude || old.longitude != m.longitude {
                        let to = m.coordinate
                        UIView.animate(withDuration: 0.9, delay: 0, options: [.curveEaseOut, .allowUserInteraction]) {
                            ann.coordinate = to
                        }
                    }
                } else {
                    let ann = RIQAnnotation(m)
                    annotations[m.id] = ann
                    map.addAnnotation(ann)
                }
            }
        }

        private func allCoordinates() -> [CLLocationCoordinate2D] {
            var pts: [CLLocationCoordinate2D] = parent.markers.map { $0.coordinate }
            for l in parent.lines { pts.append(contentsOf: l.coordinates) }
            return pts.filter { CLLocationCoordinate2DIsValid($0) && !($0.latitude == 0 && $0.longitude == 0) }
        }

        func handleFit(_ map: MKMapView) {
            let pts = allCoordinates()
            let keyChanged = parent.fitKey != nil && parent.fitKey != lastFitKey
            if pts.isEmpty { return }
            if !fitted || keyChanged {
                fitted = true
                lastFitKey = parent.fitKey
                if parent.centerOn == nil || keyChanged { fit(map, pts) }
            }
        }

        func handleCenter(_ map: MKMapView) {
            guard let c = parent.centerOn, CLLocationCoordinate2DIsValid(c) else { return }
            if let l = lastCenter, l.latitude == c.latitude, l.longitude == c.longitude { return }
            let first = lastCenter == nil
            lastCenter = c
            if first {
                let region = MKCoordinateRegion(center: c, latitudinalMeters: parent.centerZoomMeters,
                                                longitudinalMeters: parent.centerZoomMeters)
                map.setRegion(region, animated: false)
            } else {
                map.setCenter(c, animated: true)
            }
        }

        private func fit(_ map: MKMapView, _ pts: [CLLocationCoordinate2D]) {
            if pts.count == 1, let p = pts.first {
                map.setRegion(MKCoordinateRegion(center: p, latitudinalMeters: 1500, longitudinalMeters: 1500), animated: true)
                return
            }
            var rect = MKMapRect.null
            for p in pts {
                let mp = MKMapPoint(p)
                rect = rect.union(MKMapRect(x: mp.x, y: mp.y, width: 0.1, height: 0.1))
            }
            let pad = UIEdgeInsets(top: 60, left: 50, bottom: 60, right: 50)
            map.setVisibleMapRect(rect, edgePadding: pad, animated: true)
        }

        // MARK: MKMapViewDelegate

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let pl = overlay as? RIQPolyline {
                let r = MKPolylineRenderer(polyline: pl)
                r.strokeColor = pl.color
                r.lineWidth = pl.width
                r.lineCap = .round
                r.lineJoin = .round
                if pl.dashed { r.lineDashPattern = [6, 6] }
                return r
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let ann = annotation as? RIQAnnotation else { return nil }   // user location → default
            let m = ann.marker
            let hasCallout = (m.title ?? "").isEmpty == false
            let tappable = parent.onMarkerTap != nil && m.tag != nil
            switch m.style {
            case .pin:
                let id = "riq.pin"
                let v = (mapView.dequeueReusableAnnotationView(withIdentifier: id) as? MKMarkerAnnotationView)
                    ?? MKMarkerAnnotationView(annotation: ann, reuseIdentifier: id)
                v.annotation = ann
                v.markerTintColor = m.color
                v.alpha = m.alpha
                v.canShowCallout = hasCallout
                v.displayPriority = .required
                v.rightCalloutAccessoryView = tappable ? UIButton(type: .detailDisclosure) : nil
                return v
            case .dot, .liveDot:
                let id = m.style == .liveDot ? "riq.live" : "riq.dot"
                let v = mapView.dequeueReusableAnnotationView(withIdentifier: id)
                    ?? MKAnnotationView(annotation: ann, reuseIdentifier: id)
                v.annotation = ann
                v.image = Coordinator.dotImage(color: m.color, live: m.style == .liveDot)
                v.alpha = m.alpha
                v.canShowCallout = hasCallout
                v.displayPriority = .required
                v.layer.zPosition = 5
                v.rightCalloutAccessoryView = tappable ? UIButton(type: .detailDisclosure) : nil
                return v
            case .arrow(let bearing):
                let id = "riq.arrow"
                let v = mapView.dequeueReusableAnnotationView(withIdentifier: id)
                    ?? MKAnnotationView(annotation: ann, reuseIdentifier: id)
                v.annotation = ann
                v.image = Coordinator.arrowImage(color: m.color, bearing: bearing)
                v.canShowCallout = false
                v.isEnabled = false
                v.displayPriority = .defaultLow
                return v
            }
        }

        func mapView(_ mapView: MKMapView, annotationView view: MKAnnotationView, calloutAccessoryControlTapped control: UIControl) {
            guard let ann = view.annotation as? RIQAnnotation else { return }
            parent.onMarkerTap?(ann.marker)
        }

        // MARK: drawing

        static func dotImage(color: UIColor, live: Bool) -> UIImage {
            let d: CGFloat = 26
            let r = UIGraphicsImageRenderer(size: CGSize(width: d, height: d))
            return r.image { ctx in
                let g = ctx.cgContext
                if live {
                    g.setFillColor(color.withAlphaComponent(0.25).cgColor)
                    g.fillEllipse(in: CGRect(x: 0, y: 0, width: d, height: d))
                }
                let inner = d * 0.55
                let o = (d - inner) / 2
                let rect = CGRect(x: o, y: o, width: inner, height: inner)
                g.setFillColor(color.cgColor)
                g.fillEllipse(in: rect)
                g.setStrokeColor(UIColor.white.cgColor)
                g.setLineWidth(d * 0.07)
                g.strokeEllipse(in: rect)
            }
        }

        static func arrowImage(color: UIColor, bearing: Double) -> UIImage {
            let d: CGFloat = 18
            let r = UIGraphicsImageRenderer(size: CGSize(width: d, height: d))
            return r.image { ctx in
                let g = ctx.cgContext
                g.translateBy(x: d / 2, y: d / 2)
                g.rotate(by: CGFloat(bearing * .pi / 180))
                g.translateBy(x: -d / 2, y: -d / 2)
                let p = UIBezierPath()
                p.move(to: CGPoint(x: d / 2, y: d * 0.14))
                p.addLine(to: CGPoint(x: d * 0.80, y: d * 0.82))
                p.addLine(to: CGPoint(x: d / 2, y: d * 0.60))
                p.addLine(to: CGPoint(x: d * 0.20, y: d * 0.82))
                p.close()
                color.setFill()
                p.fill()
                UIColor.white.setStroke()
                p.lineWidth = d * 0.07
                p.stroke()
            }
        }
    }
}
