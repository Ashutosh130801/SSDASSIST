package `in`.recoveriq.app.ui.admin

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import `in`.recoveriq.app.data.OfficerLocation
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

/**
 * OpenStreetMap view (osmdroid) showing each on-duty field agent as a pin.
 * Matches the web app's Leaflet/OSM map — no Google Maps API key required.
 */
@Composable
fun OsmLiveMap(officers: List<OfficerLocation>, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                controller.setZoom(if (officers.isEmpty()) 5.0 else 12.0)
                val center = officers.firstOrNull()?.let { GeoPoint(it.latitude, it.longitude) }
                    ?: GeoPoint(20.5937, 78.9629) // India
                controller.setCenter(center)
            }
        },
        update = { map ->
            map.overlays.clear()
            officers.forEach { o ->
                val m = Marker(map)
                m.position = GeoPoint(o.latitude, o.longitude)
                m.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                m.title = o.name
                m.snippet = "Last seen: ${o.lastSeen}"
                map.overlays.add(m)
            }
            map.invalidate()
        },
    )
}
