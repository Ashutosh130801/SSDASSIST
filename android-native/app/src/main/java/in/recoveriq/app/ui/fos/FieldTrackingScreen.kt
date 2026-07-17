package `in`.recoveriq.app.ui.fos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import `in`.recoveriq.app.data.PingOut
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Muted
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline
import kotlin.math.roundToInt

@Composable
fun FieldTrackingScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("My route today", Modifier.padding(top = 12.dp, start = 4.dp))
        AsyncContent(block = { vm.repo.myTodayRoute() }) { pings, _ ->
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    InfoCard(Modifier.weight(1f)) {
                        Text("${pings.size}", fontWeight = FontWeight.Bold, color = BrandBlue,
                            style = MaterialTheme.typography.titleLarge)
                        Text("GPS points", style = MaterialTheme.typography.labelSmall, color = Muted)
                    }
                    InfoCard(Modifier.weight(1f)) {
                        Text("${routeKm(pings)} km", fontWeight = FontWeight.Bold, color = BrandBlue,
                            style = MaterialTheme.typography.titleLarge)
                        Text("Distance", style = MaterialTheme.typography.labelSmall, color = Muted)
                    }
                }
                Box(Modifier.fillMaxWidth().padding(top = 10.dp).height(440.dp)) {
                    RouteMap(pings, Modifier.fillMaxSize())
                }
            }
        }
    }
}

private fun routeKm(pings: List<PingOut>): String {
    var m = 0.0
    for (i in 1 until pings.size) m += haversine(pings[i - 1], pings[i])
    return ((m / 1000.0) * 10).roundToInt().div(10.0).toString()
}

private fun haversine(a: PingOut, b: PingOut): Double {
    val r = 6371000.0
    val p1 = Math.toRadians(a.latitude); val p2 = Math.toRadians(b.latitude)
    val dp = Math.toRadians(b.latitude - a.latitude); val dl = Math.toRadians(b.longitude - a.longitude)
    val h = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2)
    return 2 * r * Math.asin(Math.sqrt(h))
}

@Composable
private fun RouteMap(pings: List<PingOut>, modifier: Modifier) {
    val lineColor = BrandBlue.toArgb()
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                controller.setZoom(14.0)
                val center = pings.lastOrNull()?.let { GeoPoint(it.latitude, it.longitude) }
                    ?: GeoPoint(20.5937, 78.9629)
                controller.setCenter(center)
            }
        },
        update = { map ->
            map.overlays.clear()
            if (pings.isNotEmpty()) {
                val pts = pings.map { GeoPoint(it.latitude, it.longitude) }
                val line = Polyline().apply {
                    setPoints(pts)
                    outlinePaint.color = lineColor
                    outlinePaint.strokeWidth = 8f
                }
                map.overlays.add(line)
                Marker(map).apply {
                    position = pts.first(); title = "Start"
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    map.overlays.add(this)
                }
                Marker(map).apply {
                    position = pts.last(); title = "Latest"
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    map.overlays.add(this)
                }
            }
            map.invalidate()
        },
    )
}
