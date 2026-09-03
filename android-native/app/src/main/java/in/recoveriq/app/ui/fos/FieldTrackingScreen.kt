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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import `in`.recoveriq.app.ui.common.Actions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.RoutePoint
import `in`.recoveriq.app.data.TodayRoute
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.addDirectionArrows
import `in`.recoveriq.app.ui.common.animateMarker
import `in`.recoveriq.app.ui.common.fosPin
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
    val scope = rememberCoroutineScope()
    var route by remember { mutableStateOf<TodayRoute?>(null) }
    // My allocated cases (loaded once) — shown as pins so I can see where to go, not just my trail.
    var cases by remember { mutableStateOf<List<Case>>(emptyList()) }
    LaunchedEffect(Unit) {
        cases = runCatching { vm.repo.myCases() }.getOrDefault(emptyList())
    }
    // Live refresh: re-pull my route every few seconds so the pin moves as I do.
    LaunchedEffect(Unit) {
        while (true) {
            route = runCatching { vm.repo.myTodayRoute() }.getOrNull() ?: route
            delay(4000)
        }
    }
    val r = route
    val located = cases.count { it.latitude != null && it.longitude != null }
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("My route + allocated cases", Modifier.padding(top = 12.dp, start = 4.dp))
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            InfoCard(Modifier.weight(1f)) {
                Text("${r?.count ?: 0}", fontWeight = FontWeight.Bold, color = BrandBlue,
                    style = MaterialTheme.typography.titleLarge)
                Text("GPS points", style = MaterialTheme.typography.labelSmall, color = Muted)
            }
            InfoCard(Modifier.weight(1f)) {
                Text("${r?.distanceKm ?: 0.0} km", fontWeight = FontWeight.Bold, color = BrandBlue,
                    style = MaterialTheme.typography.titleLarge)
                Text("Distance", style = MaterialTheme.typography.labelSmall, color = Muted)
            }
            InfoCard(Modifier.weight(1f)) {
                Text("$located", fontWeight = FontWeight.Bold, color = BrandBlue,
                    style = MaterialTheme.typography.titleLarge)
                Text("Cases on map", style = MaterialTheme.typography.labelSmall, color = Muted)
            }
        }
        Box(Modifier.fillMaxWidth().padding(top = 10.dp).height(440.dp)) {
            LiveRouteMap(r?.points ?: emptyList(), cases, scope, Modifier.fillMaxSize())
        }
        if (cases.isNotEmpty() && located == 0) {
            Text("No case locations yet — an admin needs to run \"Geocode addresses\" so your cases pin on the map.",
                style = MaterialTheme.typography.labelSmall, color = Muted,
                modifier = Modifier.padding(top = 6.dp, start = 4.dp))
        }
    }
}

/** Holds overlay references that must survive recompositions so the pin can glide, not jump. */
private class RouteMapHolder {
    var rider: Marker? = null
    var centered = false
    var caseMarkers: List<Marker>? = null      // built once from the allocated cases
}

@Composable
private fun LiveRouteMap(points: List<RoutePoint>, cases: List<Case>, scope: CoroutineScope, modifier: Modifier) {
    val lineColor = BrandBlue.toArgb()
    val holder = remember { RouteMapHolder() }
    val context = LocalContext.current
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            Configuration.getInstance().userAgentValue = ctx.packageName
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)
                controller.setZoom(13.0)
                controller.setCenter(points.lastOrNull()?.let { GeoPoint(it.lat, it.lng) }
                    ?: cases.firstOrNull { it.latitude != null && it.longitude != null }
                        ?.let { GeoPoint(it.latitude!!, it.longitude!!) }
                    ?: GeoPoint(20.5937, 78.9629))
            }
        },
        update = { map ->
            map.overlays.clear()
            // Build the allocated-case pins once, then just re-add them each refresh (cheap, no thrash).
            if (holder.caseMarkers == null) {
                holder.caseMarkers = cases.filter { it.latitude != null && it.longitude != null }.map { c ->
                    Marker(map).apply {
                        position = GeoPoint(c.latitude!!, c.longitude!!)
                        val approx = c.locationSource != "field" &&
                            (c.geoPrecision == "pincode" || c.geoPrecision == "city")
                        title = (c.customerName ?: "Case #${c.id}") + if (approx) "  (approx)" else ""
                        snippet = listOfNotNull(
                            c.bank,
                            "Pending ₹${c.pendingAmount.toInt()}",
                            "Tap to navigate",
                        ).joinToString(" · ")
                        setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                        setOnMarkerClickListener { m, _ ->
                            m.showInfoWindow()
                            Actions.navigate(context, c.latitude, c.longitude, c.customerName)
                            true
                        }
                    }
                }
            }
            holder.caseMarkers?.forEach { map.overlays.add(it) }
            val geo = points.map { GeoPoint(it.lat, it.lng) }
            if (geo.isNotEmpty()) {
                val line = Polyline().apply {
                    setPoints(geo)
                    outlinePaint.color = lineColor
                    outlinePaint.strokeWidth = 8f
                }
                map.overlays.add(line)
                addDirectionArrows(map, geo, lineColor)
                Marker(map).apply {
                    position = geo.first(); title = "Start"
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    map.overlays.add(this)
                }
                val last = geo.last()
                val rider = holder.rider
                if (rider == null) {
                    val m = fosPin(map, last, lineColor, live = true, label = "You")
                    holder.rider = m; map.overlays.add(m)
                } else {
                    map.overlays.add(rider)
                    animateMarker(scope, map, rider, last)   // glide to the newest fix
                }
                if (!holder.centered) { map.controller.setCenter(last); holder.centered = true }
                else map.controller.animateTo(last)
            }
            map.invalidate()
        },
    )
}
