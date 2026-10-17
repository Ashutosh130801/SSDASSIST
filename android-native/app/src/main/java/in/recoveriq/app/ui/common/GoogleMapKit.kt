package `in`.recoveriq.app.ui.common

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.GoogleMap
import com.google.android.gms.maps.MapView
import com.google.android.gms.maps.MapsInitializer
import com.google.android.gms.maps.model.BitmapDescriptor
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.LatLngBounds
import com.google.android.gms.maps.model.Marker
import com.google.android.gms.maps.model.MarkerOptions
import com.google.android.gms.maps.model.Polyline
import com.google.android.gms.maps.model.PolylineOptions
import `in`.recoveriq.app.BuildConfig
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.OfficerLocation
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint
import kotlin.math.max
import kotlin.math.pow

/**
 * Google Maps (Maps SDK for Android) versions of the in-app maps. Free and unlimited on Android
 * in India. Used whenever the build has a MAPS_API_KEY; otherwise the screens fall back to the
 * OpenStreetMap (osmdroid) maps, so a build without a key still works.
 */
val useGoogleMaps: Boolean get() = BuildConfig.HAS_MAPS_KEY

// ---------------------------------------------------------------- lifecycle-aware MapView
@Composable
private fun rememberGoogleMapView(): MapView {
    val ctx = LocalContext.current
    val mapView = remember { MapsInitializer.initialize(ctx.applicationContext); MapView(ctx).apply { onCreate(Bundle()) } }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, mapView) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                else -> {}
            }
        }
        lifecycle.addObserver(obs)
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) mapView.onStart()
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) mapView.onResume()
        onDispose {
            lifecycle.removeObserver(obs)
            runCatching { mapView.onPause(); mapView.onStop(); mapView.onDestroy() }
        }
    }
    return mapView
}

// ---------------------------------------------------------------- icons
private fun pinBitmap(ctx: Context, colorArgb: Int, live: Boolean): BitmapDescriptor {
    val d = (ctx.resources.displayMetrics.density * 26).toInt()
    val bmp = Bitmap.createBitmap(d, d, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp); val r = d / 2f
    if (live) c.drawCircle(r, r, r, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = (colorArgb and 0x00FFFFFF) or 0x40000000 })
    c.drawCircle(r, r, r * 0.55f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = colorArgb })
    c.drawCircle(r, r, r * 0.55f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = d * 0.07f
    })
    return BitmapDescriptorFactory.fromBitmap(bmp)
}

private fun arrowUp(ctx: Context, colorArgb: Int): BitmapDescriptor {
    val d = max(24, (ctx.resources.displayMetrics.density * 16).toInt())
    val bmp = Bitmap.createBitmap(d, d, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp)
    val path = Path().apply {
        moveTo(d / 2f, d * 0.14f); lineTo(d * 0.80f, d * 0.82f); lineTo(d / 2f, d * 0.60f); lineTo(d * 0.20f, d * 0.82f); close()
    }
    c.drawPath(path, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = colorArgb })
    c.drawPath(path, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = d * 0.07f })
    return BitmapDescriptorFactory.fromBitmap(bmp)
}

private fun bearing(a: LatLng, b: LatLng): Float =
    bearingDeg(GeoPoint(a.latitude, a.longitude), GeoPoint(b.latitude, b.longitude)).toFloat()

/** Heading arrows along a route (rotated flat markers). */
private fun addArrows(ctx: Context, map: GoogleMap, pts: List<LatLng>, colorArgb: Int, count: Int = 14): List<Marker> {
    val out = ArrayList<Marker>()
    if (pts.size < 2) return out
    val icon = arrowUp(ctx, colorArgb)
    val step = max(1, pts.size / count)
    var i = step
    while (i < pts.size) {
        val a = pts[i - 1]; val b = pts[i]
        if (a != b) map.addMarker(MarkerOptions().position(b).icon(icon).anchor(0.5f, 0.5f).flat(true)
            .rotation(bearing(a, b)))?.let { out.add(it) }
        i += step
    }
    return out
}

/** Glide a marker to [to] (ease-out), like the osmdroid version. */
private fun glide(scope: CoroutineScope, marker: Marker, to: LatLng, durationMs: Long = 900): Job? {
    val from = marker.position
    if (from == to) return null
    return scope.launch {
        val steps = 30
        for (s in 1..steps) {
            val e = 1f - (1f - s.toFloat() / steps).pow(3)
            marker.position = LatLng(from.latitude + (to.latitude - from.latitude) * e,
                from.longitude + (to.longitude - from.longitude) * e)
            delay(durationMs / steps)
        }
    }
}

private fun fit(map: GoogleMap, pts: List<LatLng>, padPx: Int = 90) {
    if (pts.isEmpty()) return
    if (pts.size == 1) { map.moveCamera(CameraUpdateFactory.newLatLngZoom(pts[0], 15f)); return }
    val b = LatLngBounds.builder(); pts.forEach { b.include(it) }
    runCatching { map.moveCamera(CameraUpdateFactory.newLatLngBounds(b.build(), padPx)) }
}

private fun baseSetup(gm: GoogleMap) {
    gm.uiSettings.isZoomControlsEnabled = true
    gm.uiSettings.isMapToolbarEnabled = false
    gm.uiSettings.isCompassEnabled = true
}

// ================================================================ Admin / HO / TL live map
private class LiveHolder {
    val pins = HashMap<Int, Marker>()
    val trails = HashMap<Int, Polyline>()
    val last = HashMap<Int, LatLng>()
    var centered = false
    var route: Polyline? = null
    val routeMarks = ArrayList<Marker>()
    var routeSig = ""
}

/** Every on-duty agent as a gliding pin with a breadcrumb trail; optional day-route overlay. */
@Composable
fun GoogleLiveMap(
    officers: List<OfficerLocation>,
    scope: CoroutineScope,
    modifier: Modifier = Modifier,
    routePoints: List<GeoPoint> = emptyList(),
) {
    val ctx = LocalContext.current
    val mapView = rememberGoogleMapView()
    var gMap by remember { mutableStateOf<GoogleMap?>(null) }
    val holder = remember { LiveHolder() }
    val liveColor = Color.rgb(0x16, 0xA3, 0x4A)
    AndroidView(modifier = modifier, factory = {
        mapView.getMapAsync { gm ->
            baseSetup(gm)
            gm.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(20.5937, 78.9629), 4.5f))
            gMap = gm
        }
        mapView
    }, update = {
        val gm = gMap
        if (gm != null) drawLive(ctx, gm, holder, officers, scope, routePoints, liveColor)
    })
}

private fun drawLive(ctx: Context, gm: GoogleMap, holder: LiveHolder, officers: List<OfficerLocation>,
                     scope: CoroutineScope, routePoints: List<GeoPoint>, liveColor: Int) {
    // ---- day-route overlay ----
    val sig = if (routePoints.isEmpty()) "" else
        "${routePoints.size}:${routePoints.first().latitude},${routePoints.first().longitude}:${routePoints.last().latitude},${routePoints.last().longitude}"
    if (sig != holder.routeSig) {
        holder.route?.remove(); holder.route = null
        holder.routeMarks.forEach { it.remove() }; holder.routeMarks.clear()
        val pts = routePoints.map { LatLng(it.latitude, it.longitude) }
        if (pts.size >= 2) {
            val blue = Color.rgb(0x25, 0x63, 0xEB)
            holder.route = gm.addPolyline(PolylineOptions().addAll(pts).color(blue).width(10f).zIndex(1f))
            holder.routeMarks.addAll(addArrows(ctx, gm, pts, blue))
            gm.addMarker(MarkerOptions().position(pts.first()).title("Start").icon(pinBitmap(ctx, liveColor, true)).anchor(0.5f, 0.5f))?.let { holder.routeMarks.add(it) }
            gm.addMarker(MarkerOptions().position(pts.last()).title("End").icon(pinBitmap(ctx, Color.rgb(0xDC, 0x26, 0x26), false)).anchor(0.5f, 0.5f))?.let { holder.routeMarks.add(it) }
            fit(gm, pts)
        }
        holder.routeSig = sig
    }
    // ---- live officers ----
    val liveIds = HashSet<Int>()
    officers.forEach { o ->
        liveIds.add(o.officerId)
        val to = LatLng(o.latitude, o.longitude)
        val prev = holder.last[o.officerId]
        val pin = holder.pins[o.officerId]
        if (pin == null) {
            gm.addMarker(MarkerOptions().position(to).title(o.name).snippet("Last seen: ${o.lastSeen}")
                .icon(pinBitmap(ctx, liveColor, true)).anchor(0.5f, 0.5f).zIndex(3f))?.let { holder.pins[o.officerId] = it }
        } else {
            pin.title = o.name; pin.snippet = "Last seen: ${o.lastSeen}"
            glide(scope, pin, to)
        }
        if (prev != null && prev != to) {
            val tr = holder.trails.getOrPut(o.officerId) {
                gm.addPolyline(PolylineOptions().add(prev).color((liveColor and 0x00FFFFFF) or 0x96000000.toInt()).width(7f))
            }
            tr.points = tr.points + to
        }
        holder.last[o.officerId] = to
    }
    (holder.pins.keys - liveIds).toList().forEach { gone ->
        holder.pins.remove(gone)?.remove(); holder.trails.remove(gone)?.remove(); holder.last.remove(gone)
    }
    if (!holder.centered && officers.isNotEmpty() && routePoints.isEmpty()) {
        fit(gm, officers.map { LatLng(it.latitude, it.longitude) })
        holder.centered = true
    }
}

// ================================================================ FOS: my route + my cases
private class RouteHolder {
    var rider: Marker? = null
    var line: Polyline? = null
    val arrows = ArrayList<Marker>()
    var start: Marker? = null
    var casesDrawn = false
    var centered = false
    var sig = ""
}

/** The FOS's own live route (gliding "You" pin + heading arrows) and pins for his allocated cases. */
@Composable
fun GoogleRouteMap(
    points: List<LatLng>,
    cases: List<Case>,
    scope: CoroutineScope,
    lineColor: Int,
    modifier: Modifier = Modifier,
) {
    val ctx = LocalContext.current
    val mapView = rememberGoogleMapView()
    var gMap by remember { mutableStateOf<GoogleMap?>(null) }
    val holder = remember { RouteHolder() }
    AndroidView(modifier = modifier, factory = {
        mapView.getMapAsync { gm ->
            baseSetup(gm)
            gm.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(20.5937, 78.9629), 4.5f))
            gm.setOnInfoWindowClickListener { m ->
                (m.tag as? Case)?.let { c -> Actions.navigate(ctx, c.latitude, c.longitude, c.customerName) }
            }
            gMap = gm
        }
        mapView
    }, update = {
        val gm = gMap
        if (gm != null) drawRoute(ctx, gm, holder, points, cases, scope, lineColor)
    })
}

private fun drawRoute(ctx: Context, gm: GoogleMap, holder: RouteHolder, points: List<LatLng>,
                      cases: List<Case>, scope: CoroutineScope, lineColor: Int) {
    // Allocated-case pins (once). Approximate pins (pincode/city level) are drawn lighter.
    if (!holder.casesDrawn && cases.isNotEmpty()) {
        cases.filter { it.latitude != null && it.longitude != null }.forEach { c ->
            val approx = c.locationSource != "field" && (c.geoPrecision == "pincode" || c.geoPrecision == "city")
            gm.addMarker(MarkerOptions().position(LatLng(c.latitude!!, c.longitude!!))
                .title((c.customerName ?: "Case #${c.id}") + if (approx) "  (approx)" else "")
                .snippet(listOfNotNull(c.bank, "Pending ₹${c.pendingAmount.toInt()}", "Tap here to navigate").joinToString(" · "))
                .icon(BitmapDescriptorFactory.defaultMarker(if (approx) BitmapDescriptorFactory.HUE_ORANGE else BitmapDescriptorFactory.HUE_RED))
                .alpha(if (approx) 0.7f else 1f))?.tag = c
        }
        holder.casesDrawn = true
        if (points.isEmpty() && !holder.centered) {
            fit(gm, cases.filter { it.latitude != null }.map { LatLng(it.latitude!!, it.longitude!!) }); holder.centered = true
        }
    }
    if (points.isEmpty()) return
    val sig = "${points.size}:${points.last().latitude},${points.last().longitude}"
    if (sig != holder.sig) {
        holder.line?.remove()
        holder.line = gm.addPolyline(PolylineOptions().addAll(points).color(lineColor).width(11f).zIndex(1f))
        holder.arrows.forEach { it.remove() }; holder.arrows.clear()
        holder.arrows.addAll(addArrows(ctx, gm, points, lineColor))
        if (holder.start == null) holder.start = gm.addMarker(MarkerOptions().position(points.first()).title("Start"))
        val last = points.last()
        val rider = holder.rider
        if (rider == null) {
            holder.rider = gm.addMarker(MarkerOptions().position(last).title("You")
                .icon(pinBitmap(ctx, lineColor, true)).anchor(0.5f, 0.5f).zIndex(5f))
        } else glide(scope, rider, last)
        if (!holder.centered) { gm.moveCamera(CameraUpdateFactory.newLatLngZoom(last, 15f)); holder.centered = true }
        else gm.animateCamera(CameraUpdateFactory.newLatLng(last))
        holder.sig = sig
    }
}
