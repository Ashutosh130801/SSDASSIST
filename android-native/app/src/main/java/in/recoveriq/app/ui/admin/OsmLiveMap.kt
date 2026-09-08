package `in`.recoveriq.app.ui.admin

import android.graphics.Color
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.CoroutineScope
import `in`.recoveriq.app.data.OfficerLocation
import `in`.recoveriq.app.ui.common.animateMarker
import `in`.recoveriq.app.ui.common.fosPin
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

/**
 * OpenStreetMap (osmdroid) view of every on-duty field agent — Swiggy/Zomato style.
 * Each agent keeps one persistent pin that *glides* to its new GPS fix and trails a
 * breadcrumb line as it moves. Matches the web Leaflet/OSM map — no Google key needed.
 */

private class LiveOverlayHolder {
    val pins = HashMap<Int, Marker>()
    val trails = HashMap<Int, Polyline>()
    val last = HashMap<Int, GeoPoint>()
    var centered = false
    // Route-history overlay (drawn when a specific officer's day is opened)
    var route: Polyline? = null
    val routeMarks = ArrayList<Marker>()
    var routeSig: String = ""
}

@Composable
fun OsmLiveMap(
    officers: List<OfficerLocation>,
    scope: CoroutineScope,
    modifier: Modifier = Modifier,
    routePoints: List<GeoPoint> = emptyList(),
) {
    val holder = remember { LiveOverlayHolder() }
    val liveColor = Color.rgb(0x16, 0xA3, 0x4A)   // green = live
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                // Lock to a single world copy so the map can't be flung into infinite repeats,
                // and clamp scrolling/zoom to the real world bounds.
                isHorizontalMapRepetitionEnabled = false
                isVerticalMapRepetitionEnabled = false
                setScrollableAreaLimitLatitude(
                    org.osmdroid.views.MapView.getTileSystem().maxLatitude,
                    org.osmdroid.views.MapView.getTileSystem().minLatitude, 0,
                )
                setScrollableAreaLimitLongitude(-180.0, 180.0, 0)
                minZoomLevel = 3.0
                maxZoomLevel = 19.0
                controller.setZoom(if (officers.isEmpty()) 5.0 else 12.0)
                controller.setCenter(
                    officers.firstOrNull()?.let { GeoPoint(it.latitude, it.longitude) }
                        ?: GeoPoint(20.5937, 78.9629),
                )
            }
        },
        update = { map ->
            // ---- route-history overlay: redraw only when the point set changes ----
            val sig = if (routePoints.isEmpty()) "" else
                "${routePoints.size}:${routePoints.first().latitude},${routePoints.first().longitude}:" +
                    "${routePoints.last().latitude},${routePoints.last().longitude}"
            if (sig != holder.routeSig) {
                holder.route?.let { map.overlays.remove(it) }; holder.route = null
                holder.routeMarks.forEach { map.overlays.remove(it) }; holder.routeMarks.clear()
                if (routePoints.size >= 2) {
                    val line = Polyline().apply {
                        outlinePaint.color = Color.rgb(0x25, 0x63, 0xEB)
                        outlinePaint.strokeWidth = 7f
                        setPoints(routePoints)
                    }
                    map.overlays.add(0, line); holder.route = line
                    val s = fosPin(map, routePoints.first(), Color.rgb(0x16, 0xA3, 0x4A), live = true, label = "S")
                    val e = fosPin(map, routePoints.last(), Color.rgb(0xDC, 0x26, 0x26), live = false, label = "E")
                    holder.routeMarks.add(s); holder.routeMarks.add(e)
                    map.overlays.add(s); map.overlays.add(e)
                    // Fit the day's route into view.
                    val lats = routePoints.map { it.latitude }; val lngs = routePoints.map { it.longitude }
                    val bb = org.osmdroid.util.BoundingBox(lats.maxOrNull()!!, lngs.maxOrNull()!!,
                        lats.minOrNull()!!, lngs.minOrNull()!!)
                    map.post { runCatching { map.zoomToBoundingBox(bb.increaseByScale(1.4f), true, 60) } }
                }
                holder.routeSig = sig
            }
            val liveIds = HashSet<Int>()
            officers.forEach { o ->
                liveIds.add(o.officerId)
                val to = GeoPoint(o.latitude, o.longitude)
                val prev = holder.last[o.officerId]
                var pin = holder.pins[o.officerId]
                if (pin == null) {
                    pin = fosPin(map, to, liveColor, live = true, label = o.name)
                    pin.snippet = "Last seen: ${o.lastSeen}"
                    holder.pins[o.officerId] = pin
                    map.overlays.add(pin)
                } else {
                    pin.title = o.name
                    pin.snippet = "Last seen: ${o.lastSeen}"
                    animateMarker(scope, map, pin, to)   // smooth glide to the new fix
                }
                // extend a live breadcrumb trail as the agent moves
                if (prev != null && (prev.latitude != to.latitude || prev.longitude != to.longitude)) {
                    val tr = holder.trails.getOrPut(o.officerId) {
                        Polyline().apply {
                            outlinePaint.color = liveColor
                            outlinePaint.strokeWidth = 5f
                            outlinePaint.alpha = 150
                            setPoints(mutableListOf(prev))
                            map.overlays.add(0, this)
                        }
                    }
                    tr.addPoint(to)
                }
                holder.last[o.officerId] = to
            }
            // drop agents that left the live feed
            (holder.pins.keys - liveIds).toList().forEach { gone ->
                holder.pins.remove(gone)?.let { map.overlays.remove(it) }
                holder.trails.remove(gone)?.let { map.overlays.remove(it) }
                holder.last.remove(gone)
            }
            if (!holder.centered && officers.isNotEmpty()) {
                map.controller.setZoom(12.0)
                map.controller.setCenter(GeoPoint(officers[0].latitude, officers[0].longitude))
                holder.centered = true
            }
            map.invalidate()
        },
    )
}
