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
import `in`.recoveriq.app.data.RoutePoint
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

@Composable
fun FieldTrackingScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("My route today", Modifier.padding(top = 12.dp, start = 4.dp))
        AsyncContent(block = { vm.repo.myTodayRoute() }) { route, _ ->
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    InfoCard(Modifier.weight(1f)) {
                        Text("${route.count}", fontWeight = FontWeight.Bold, color = BrandBlue,
                            style = MaterialTheme.typography.titleLarge)
                        Text("GPS points", style = MaterialTheme.typography.labelSmall, color = Muted)
                    }
                    InfoCard(Modifier.weight(1f)) {
                        Text("${route.distanceKm} km", fontWeight = FontWeight.Bold, color = BrandBlue,
                            style = MaterialTheme.typography.titleLarge)
                        Text("Distance", style = MaterialTheme.typography.labelSmall, color = Muted)
                    }
                }
                Box(Modifier.fillMaxWidth().padding(top = 10.dp).height(440.dp)) {
                    RouteMap(route.points, Modifier.fillMaxSize())
                }
            }
        }
    }
}

@Composable
private fun RouteMap(points: List<RoutePoint>, modifier: Modifier) {
    val lineColor = BrandBlue.toArgb()
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                controller.setZoom(14.0)
                val center = points.lastOrNull()?.let { GeoPoint(it.lat, it.lng) }
                    ?: GeoPoint(20.5937, 78.9629)
                controller.setCenter(center)
            }
        },
        update = { map ->
            map.overlays.clear()
            if (points.isNotEmpty()) {
                val pts = points.map { GeoPoint(it.lat, it.lng) }
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
