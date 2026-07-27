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
}

@Composable
fun OsmLiveMap(officers: List<OfficerLocation>, scope: CoroutineScope, modifier: Modifier = Modifier) {
    val holder = remember { LiveOverlayHolder() }
    val liveColor = Color.rgb(0x16, 0xA3, 0x4A)   // green = live
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                controller.setZoom(if (officers.isEmpty()) 5.0 else 12.0)
                controller.setCenter(
                    officers.firstOrNull()?.let { GeoPoint(it.latitude, it.longitude) }
                        ?: GeoPoint(20.5937, 78.9629),
                )
            }
        },
        update = { map ->
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
