package `in`.recoveriq.app.ui.common

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import androidx.core.graphics.drawable.toDrawable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin

/**
 * Shared osmdroid helpers for the live-tracking maps:
 *  - direction arrows along a route (which way the agent was heading),
 *  - a "live rider" pin, and
 *  - smooth Swiggy/Zomato-style marker gliding between GPS fixes.
 */

/** Compass bearing in degrees (0 = north, clockwise) from point a to point b. */
fun bearingDeg(a: GeoPoint, b: GeoPoint): Double {
    val lat1 = Math.toRadians(a.latitude); val lat2 = Math.toRadians(b.latitude)
    val dLon = Math.toRadians(b.longitude - a.longitude)
    val y = sin(dLon) * cos(lat2)
    val x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dLon)
    return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
}

/** An arrowhead bitmap already rotated to point along [bearing] (canvas rotate = clockwise). */
private fun arrowBitmap(ctx: Context, colorArgb: Int, bearing: Double): Bitmap {
    val d = max(24, (ctx.resources.displayMetrics.density * 16).toInt())
    val bmp = Bitmap.createBitmap(d, d, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp)
    val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = colorArgb; style = Paint.Style.FILL }
    val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = d * 0.07f
    }
    c.save()
    c.rotate(bearing.toFloat(), d / 2f, d / 2f)   // arrow drawn pointing up, then rotated to heading
    val path = Path().apply {
        moveTo(d / 2f, d * 0.14f)
        lineTo(d * 0.80f, d * 0.82f)
        lineTo(d / 2f, d * 0.60f)
        lineTo(d * 0.20f, d * 0.82f)
        close()
    }
    c.drawPath(path, fill); c.drawPath(path, edge)
    c.restore()
    return bmp
}

/** Sprinkle ~[count] heading arrows along [pts]; returns the markers added to [map]. */
fun addDirectionArrows(map: MapView, pts: List<GeoPoint>, colorArgb: Int, count: Int = 14): List<Marker> {
    val out = ArrayList<Marker>()
    if (pts.size < 2) return out
    val step = max(1, pts.size / count)
    var i = step
    while (i < pts.size) {
        val a = pts[i - 1]; val b = pts[i]
        if (a.latitude != b.latitude || a.longitude != b.longitude) {
            val m = Marker(map).apply {
                position = b
                icon = arrowBitmap(map.context, colorArgb, bearingDeg(a, b)).toDrawable(map.context.resources)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                isFlat = true
                setInfoWindow(null)
            }
            map.overlays.add(m); out.add(m)
        }
        i += step
    }
    return out
}

/** A round "live rider" pin: soft halo (when [live]) + solid dot with a white ring. */
fun fosPin(map: MapView, at: GeoPoint, colorArgb: Int, live: Boolean, label: String? = null): Marker {
    val ctx = map.context
    val d = (ctx.resources.displayMetrics.density * 26).toInt()
    val bmp = Bitmap.createBitmap(d, d, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp)
    val r = d / 2f
    if (live) {
        c.drawCircle(r, r, r, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = (colorArgb and 0x00FFFFFF) or 0x40000000   // translucent halo
        })
    }
    c.drawCircle(r, r, r * 0.55f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = colorArgb })
    c.drawCircle(r, r, r * 0.55f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = d * 0.07f
    })
    return Marker(map).apply {
        position = at
        icon = bmp.toDrawable(ctx.resources)
        setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        title = label   // tap shows name/snippet via the default info window
    }
}

/** Glide [marker] from its current position to [to] over [durationMs] (ease-out). */
fun animateMarker(scope: CoroutineScope, map: MapView, marker: Marker, to: GeoPoint, durationMs: Long = 900): Job? {
    val from = marker.position
    if (from == null) { marker.position = to; map.invalidate(); return null }
    if (from.latitude == to.latitude && from.longitude == to.longitude) return null
    return scope.launch {
        val steps = 30
        for (s in 1..steps) {
            val k = s.toFloat() / steps
            val e = 1f - (1f - k).pow(3)   // ease-out cubic
            marker.position = GeoPoint(
                from.latitude + (to.latitude - from.latitude) * e,
                from.longitude + (to.longitude - from.longitude) * e,
            )
            map.invalidate()
            delay(durationMs / steps)
        }
    }
}
