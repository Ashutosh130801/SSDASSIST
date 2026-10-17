package `in`.recoveriq.app.ui.detail

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Typeface
import android.location.Geocoder
import android.media.ExifInterface
import android.net.Uri
import android.os.Build
import android.os.Looper
import android.os.SystemClock
import android.location.Location
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.viewinterop.AndroidView
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.GoogleMap
import com.google.android.gms.maps.GoogleMapOptions
import com.google.android.gms.maps.MapView
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.MarkerOptions
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import `in`.recoveriq.app.ui.common.DatePickerField
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.ByteArrayOutputStream
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/** Result payload the caller uploads via Repository.createVisit(...). */
data class VisitDraft(
    val lat: Double?, val lng: Double?, val accuracy: Double?,
    val personMoved: Boolean, val paid: Boolean, val amount: Double,
    val disposition: String?, val note: String?, val photoJpeg: ByteArray?,
    val normStab: String? = null,
    val ptpDate: String? = null,
    val paymentPhotoJpeg: ByteArray? = null,   // payment screenshot the customer shared (optional)
    val addressSlot: String? = null,           // '1' / '2' / '3' / 'new' — which address was visited
    val addressText: String? = null,           // that address (for the WhatsApp visit slip)
    val gpsMock: Boolean = false,              // phone reported a fake-GPS (mock) location
    val gpsFixAgeS: Double? = null,            // age of the GPS fix when the photo was taken
    val gpsPincode: String? = null,            // pincode where the photo was taken
    val gpsAddress: String? = null,            // address the phone detected at the photo spot
    val gpsCity: String? = null,               // city of that detected address
)

/** One of the customer's addresses the FOS can say he visited. */
data class VisitAddress(val key: String, val label: String, val text: String)

/** A frozen GPS reading (taken the moment the photo is shot). */
private data class Fix(val lat: Double, val lng: Double, val acc: Double?, val mock: Boolean, val ageS: Double)

private const val GOOD_ACC_M = 30.0        // wait for at least this accuracy before the photo

private fun Location.mockFlag(): Boolean =
    if (Build.VERSION.SDK_INT >= 31) isMock else @Suppress("DEPRECATION") isFromMockProvider

private fun Location.ageSeconds(): Double =
    (SystemClock.elapsedRealtimeNanos() - elapsedRealtimeNanos) / 1e9

// ---------------------------------------------------------------------------
// GPS-stamp helpers — replicate a "GPS Map Camera": the captured photo is
// watermarked with the live coordinates, accuracy, address and IST timestamp,
// so the image itself is tamper-proof proof of where/when the visit happened.
// ---------------------------------------------------------------------------

private fun decodeSampled(file: File, maxPx: Int): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.absolutePath, bounds)
    if (bounds.outWidth <= 0) return null
    var sample = 1
    val longest = maxOf(bounds.outWidth, bounds.outHeight)
    while (longest / sample > maxPx) sample *= 2
    val opts = BitmapFactory.Options().apply { inSampleSize = sample }
    return BitmapFactory.decodeFile(file.absolutePath, opts)
}

/**
 * Fetch a small OpenStreetMap tile centred on the fix and drop a red pin at the exact
 * position — this is the little map thumbnail the GPS Map Camera app shows.
 */
private fun fetchMapThumb(lat: Double, lng: Double): Bitmap? = runCatching {
    val z = 16
    val n = Math.pow(2.0, z.toDouble())
    val xf = (lng + 180.0) / 360.0 * n
    val latRad = Math.toRadians(lat)
    val yf = (1.0 - Math.log(Math.tan(latRad) + 1.0 / Math.cos(latRad)) / Math.PI) / 2.0 * n
    val xt = Math.floor(xf).toInt()
    val yt = Math.floor(yf).toInt()
    val url = "https://tile.openstreetmap.org/$z/$xt/$yt.png"
    val client = OkHttpClient.Builder().callTimeout(6, TimeUnit.SECONDS).build()
    val req = Request.Builder().url(url)
        .header("User-Agent", "RecoverIQ-Android/1.0 (field-visit geotag)").build()
    client.newCall(req).execute().use { resp ->
        if (!resp.isSuccessful) return@runCatching null
        val bytes = resp.body?.bytes() ?: return@runCatching null
        val tile = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@runCatching null
        val out = tile.copy(Bitmap.Config.ARGB_8888, true)
        val cv = Canvas(out)
        val px = ((xf - xt) * out.width).toFloat()
        val py = ((yf - yt) * out.height).toFloat()
        val r = out.width * 0.07f
        cv.drawCircle(px, py + r, r, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(70, 0, 0, 0) }) // shadow
        cv.drawCircle(px, py, r, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#EF4444") })
        cv.drawCircle(px, py, r * 0.38f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
        out
    }
}.getOrNull()

/** Cameras often store the photo sideways with an EXIF rotation flag — apply it. */
private fun applyExifRotation(file: File, bmp: Bitmap): Bitmap {
    return runCatching {
        val exif = ExifInterface(file.absolutePath)
        val deg = when (exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        if (deg == 0f) bmp else {
            val m = Matrix().apply { postRotate(deg) }
            Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
        }
    }.getOrDefault(bmp)
}

/** Split a line into <=maxLines lines that fit maxWidth, ellipsizing the last one. */
private fun wrap(paint: Paint, text: String, maxWidth: Float, maxLines: Int): List<String> {
    if (text.isBlank()) return emptyList()
    val words = text.split(" ")
    val lines = ArrayList<String>()
    var cur = StringBuilder()
    for (w in words) {
        val trial = if (cur.isEmpty()) w else "$cur $w"
        if (paint.measureText(trial) <= maxWidth) {
            cur = StringBuilder(trial)
        } else {
            if (cur.isNotEmpty()) lines.add(cur.toString())
            cur = StringBuilder(w)
            if (lines.size == maxLines - 1) break
        }
    }
    if (cur.isNotEmpty() && lines.size < maxLines) lines.add(cur.toString())
    // Ellipsize the final line if content still overflows.
    if (lines.isNotEmpty()) {
        val last = lines.last()
        if (paint.measureText(last) > maxWidth) {
            var s = last
            while (s.isNotEmpty() && paint.measureText("$s…") > maxWidth) s = s.dropLast(1)
            lines[lines.size - 1] = "$s…"
        }
    }
    return lines
}

/** Reverse-geocode one point → (readable address without ", India", pincode). Network/IO call. */
private fun detectAddress(ctx: android.content.Context, lat: Double, lng: Double): Triple<String?, String?, String?> = runCatching {
    @Suppress("DEPRECATION")
    val a = Geocoder(ctx, Locale.ENGLISH).getFromLocation(lat, lng, 1)?.firstOrNull() ?: return@runCatching Triple<String?, String?, String?>(null, null, null)
    val pin = a.postalCode?.takeIf { it.isNotBlank() }
    val full = a.getAddressLine(0) ?: listOfNotNull(a.featureName, a.subLocality, a.locality, a.adminArea).joinToString(", ")
    // Drop ", India" and the pincode from the text — the pincode is printed on its own line.
    var line = full.replace(Regex(",?\\s*India\\s*$"), "")
    if (pin != null) line = line.replace(Regex("\\s*$pin"), "")
    Triple(line.trim().trimEnd(',').trim().ifBlank { null }, pin, a.locality?.takeIf { it.isNotBlank() })
}.getOrDefault(Triple(null, null, null))

private fun accuracyLabel(acc: Double?): String = when {
    acc == null -> "unknown"
    acc <= 10 -> "±${acc.toInt()} m (Excellent)"
    acc <= 30 -> "±${acc.toInt()} m (Good)"
    acc <= 100 -> "±${acc.toInt()} m (Fair)"
    else -> "±${acc.toInt()} m (Weak)"
}

/** Draw the translucent geo-stamp banner across the bottom of the photo. */
private fun stampPhoto(
    src: Bitmap, lat: Double?, lng: Double?, acc: Double?, address: String?,
    agentName: String?, caseLabel: String?, mapThumb: Bitmap?, visitedLabel: String? = null,
    pincode: String? = null,
): Bitmap {
    val bmp = if (src.isMutable) src else src.copy(Bitmap.Config.ARGB_8888, true)
    val c = Canvas(bmp)
    val w = bmp.width.toFloat()
    val h = bmp.height.toFloat()
    val scale = (w / 1080f).coerceAtLeast(0.5f)
    val pad = 20f * scale
    val big = 42f * scale
    val small = 34f * scale
    val edge = 10f * scale

    val timeFmt = SimpleDateFormat("dd MMM yyyy, hh:mm:ss a", Locale.ENGLISH)
        .apply { timeZone = TimeZone.getTimeZone("Asia/Kolkata") }
    val stamp = "${timeFmt.format(Date())} IST"

    val paintBody = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; textSize = small; typeface = Typeface.DEFAULT
        setShadowLayer(4f * scale, 0f, 0f, Color.BLACK)
    }
    val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; textSize = big
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        setShadowLayer(4f * scale, 0f, 0f, Color.BLACK)
    }
    val title = "RecoverIQ • Field visit"
    val labelPaint = Paint(paintBody).apply {
        color = Color.parseColor("#FDE68A")                       // soft yellow labels
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }

    // Reserve a square on the right for the map thumbnail (if we fetched one).
    val mapSize = if (mapThumb != null) 300f * scale else 0f
    val mapGap = if (mapThumb != null) pad else 0f
    val textW = w - pad * 2 - edge - mapSize - mapGap

    // Build the lines. A leading "§" marks a highlighted (label-coloured, bold) line.
    val body = ArrayList<String>()
    agentName?.takeIf { it.isNotBlank() }?.let { body.addAll(wrap(paintBody, "Agent: $it", textW, 1)) }
    caseLabel?.takeIf { it.isNotBlank() }?.let { body.addAll(wrap(paintBody, it, textW, 1)) }
    visitedLabel?.takeIf { it.isNotBlank() }?.let { body.addAll(wrap(paintBody, "Visiting: $it", textW, 1)) }
    // ---- What the phone detected at the photo spot (the important part) ----
    body.add("§📍 Detected address")
    val addr = address?.trim()?.takeIf { it.isNotEmpty() }
    if (addr != null) body.addAll(wrap(paintBody, addr, textW, 3))
    else body.add("Address not available (no internet at photo time)")
    body.add("§PIN: ${pincode?.takeIf { it.isNotBlank() } ?: "—"}     GPS accuracy: ${accuracyLabel(acc)}")
    if (lat != null && lng != null) body.add("Lat ${"%.6f".format(lat)}   Lng ${"%.6f".format(lng)}")
    else body.add("Location unavailable")
    body.add(stamp)

    val lineGap = 1.28f
    val textBlockH = pad * 2 + big * lineGap + small * lineGap * body.size
    // Grow the panel so the map thumbnail always fits inside it.
    val panelH = maxOf(textBlockH, mapSize + pad * 2)
    val top = h - panelH

    // Dark scrim + blue accent edge.
    c.drawRect(0f, top, w, h, Paint().apply { color = Color.argb(185, 0, 0, 0) })
    c.drawRect(0f, top, edge, h, Paint().apply { color = Color.parseColor("#3B82F6") })

    // Map thumbnail on the right, vertically centred, with a white frame.
    if (mapThumb != null) {
        val mx = w - pad - mapSize
        val my = top + (panelH - mapSize) / 2f
        val frame = 3f * scale
        c.drawRect(mx - frame, my - frame, mx + mapSize + frame, my + mapSize + frame,
            Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
        val scaled = Bitmap.createScaledBitmap(mapThumb, mapSize.toInt(), mapSize.toInt(), true)
        c.drawBitmap(scaled, mx, my, null)
    }

    var y = top + pad + big
    c.drawText(title, pad + edge, y, titlePaint)
    y += big * (lineGap - 1f)
    for (ln in body) {
        y += small * lineGap
        if (ln.startsWith("§")) c.drawText(ln.substring(1), pad + edge, y, labelPaint)
        else c.drawText(ln, pad + edge, y, paintBody)
    }
    return bmp
}

@OptIn(ExperimentalLayoutApi::class)
@SuppressLint("MissingPermission")
@Composable
fun LogVisitDialog(
    isCreditCard: Boolean,
    agentName: String? = null,
    caseLabel: String? = null,
    addresses: List<VisitAddress> = emptyList(),
    onDismiss: () -> Unit,
    onSubmit: suspend (VisitDraft) -> String?,   // null = saved; non-null = error message to show
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var submitting by remember { mutableStateOf(false) }
    var submitError by remember { mutableStateOf<String?>(null) }
    val dispositions = listOf("Met customer", "Not available", "Paid", "Wrong address", "Person moved", "PTP")
    var disp by remember { mutableStateOf("Met customer") }
    var paid by remember { mutableStateOf(false) }
    var moved by remember { mutableStateOf(false) }
    var amount by remember { mutableStateOf("") }
    var normStab by remember { mutableStateOf("STAB") }
    var ptpDate by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var photo by remember { mutableStateOf<Bitmap?>(null) }
    var stamping by remember { mutableStateOf(false) }
    var paymentPhoto by remember { mutableStateOf<Bitmap?>(null) }   // payment screenshot from the customer
    var lat by remember { mutableStateOf<Double?>(null) }
    var lng by remember { mutableStateOf<Double?>(null) }
    var acc by remember { mutableStateOf<Double?>(null) }
    var address by remember { mutableStateOf<String?>(null) }
    var mapThumb by remember { mutableStateOf<Bitmap?>(null) }       // OSM fallback thumbnail
    var mock by remember { mutableStateOf(false) }
    var lastFix by remember { mutableStateOf<Location?>(null) }
    var gpsPincode by remember { mutableStateOf<String?>(null) }
    var gpsCity by remember { mutableStateOf<String?>(null) }
    var shot by remember { mutableStateOf<Fix?>(null) }               // GPS frozen at photo time
    var override by remember { mutableStateOf(false) }                // take photo despite weak GPS
    var gMap by remember { mutableStateOf<GoogleMap?>(null) }
    var slot by remember { mutableStateOf(addresses.firstOrNull()?.key ?: "1") }
    val chosen = addresses.firstOrNull { it.key == slot }
    var geocodedAt by remember { mutableStateOf<Location?>(null) }

    // A private cache file the camera writes the full-res photo into, shared via FileProvider.
    val photoFile = remember { File(context.cacheDir, "visit_${System.currentTimeMillis()}.jpg") }
    val photoUri: Uri = remember {
        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", photoFile)
    }

    // Live high-accuracy GPS while the form is open (NOT the phone's stale "last known" location).
    // Each update keeps the newest fix; the address/pincode is looked up again when he moves > 50 m.
    DisposableEffect(Unit) {
        val fused = LocationServices.getFusedLocationProviderClient(context)
        val cb = object : LocationCallback() {
            override fun onLocationResult(r: LocationResult) {
                val loc = r.lastLocation ?: return
                lastFix = loc
                lat = loc.latitude; lng = loc.longitude; acc = loc.accuracy.toDouble()
                mock = mock || loc.mockFlag()
                val g = geocodedAt
                if (g == null || g.distanceTo(loc) > 50f) {
                    geocodedAt = loc
                    scope.launch(Dispatchers.IO) {
                        val a = runCatching {
                            @Suppress("DEPRECATION")
                            Geocoder(context, Locale.ENGLISH).getFromLocation(loc.latitude, loc.longitude, 1)?.firstOrNull()
                        }.getOrNull()
                        val line = a?.let { it.getAddressLine(0) ?: listOfNotNull(it.subLocality, it.locality, it.adminArea).joinToString(", ") }
                        withContext(Dispatchers.Main) {
                            if (!line.isNullOrBlank()) address = line
                            a?.postalCode?.takeIf { it.isNotBlank() }?.let { gpsPincode = it }
                            a?.locality?.takeIf { it.isNotBlank() }?.let { gpsCity = it }
                        }
                    }
                    if (!BuildConfig.HAS_MAPS_KEY) scope.launch(Dispatchers.IO) {
                        val m = fetchMapThumb(loc.latitude, loc.longitude)
                        if (m != null) withContext(Dispatchers.Main) { mapThumb = m }
                    }
                }
            }
        }
        runCatching {
            fused.requestLocationUpdates(
                LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 2000L).setMinUpdateIntervalMillis(1000L).build(),
                cb, Looper.getMainLooper(),
            )
        }
        onDispose { runCatching { fused.removeLocationUpdates(cb) } }
    }
    // Keep the Google map preview centred on the current fix.
    LaunchedEffect(lat, lng, gMap) {
        val gm = gMap; val la = lat; val ln = lng
        if (gm != null && la != null && ln != null) {
            val p = LatLng(la, ln)
            gm.clear(); gm.addMarker(MarkerOptions().position(p))
            gm.moveCamera(CameraUpdateFactory.newLatLngZoom(p, 17f))
        }
    }
    val goodFix = lat != null && (acc ?: 999.0) <= GOOD_ACC_M

    // Pick the customer's payment screenshot from the gallery (downsampled to keep upload small).
    val paymentPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) scope.launch(Dispatchers.IO) {
            val bmp = runCatching {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return@runCatching null
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                var sample = 1
                val longest = maxOf(bounds.outWidth, bounds.outHeight)
                while (longest / sample > 1600) sample *= 2
                val opts = BitmapFactory.Options().apply { inSampleSize = sample }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
            }.getOrNull()
            if (bmp != null) withContext(Dispatchers.Main) { paymentPhoto = bmp }
        }
    }

    // Capture the payment screenshot with the camera (e.g. photo of the customer's phone screen).
    val paymentPhotoFile = remember { File(context.cacheDir, "payment_${System.currentTimeMillis()}.jpg") }
    val paymentPhotoUri: Uri = remember {
        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", paymentPhotoFile)
    }
    val paymentCamera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) scope.launch(Dispatchers.IO) {
            val bmp = runCatching {
                val raw = decodeSampled(paymentPhotoFile, 1600) ?: return@runCatching null
                applyExifRotation(paymentPhotoFile, raw)
            }.getOrNull()
            if (bmp != null) withContext(Dispatchers.Main) { paymentPhoto = bmp }
        }
    }

    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) {
            stamping = true
            scope.launch(Dispatchers.Main) {
                // Google map snapshot of the spot (falls back to the OSM thumbnail when no key/map).
                val gThumb: Bitmap? = gMap?.let { gm ->
                    withTimeoutOrNull(3000) {
                        suspendCancellableCoroutine<Bitmap?> { cont -> gm.snapshot { bmp -> if (cont.isActive) cont.resume(bmp) } }
                    }
                }
                val f = shot
                // Address + pincode of the EXACT spot the photo was taken (matches the stamped Lat/Lng).
                val (spotAddr, spotPin, spotCity) = if (f != null) withContext(Dispatchers.IO) { detectAddress(context, f.lat, f.lng) }
                                                    else Triple(address, gpsPincode, gpsCity)
                if (spotPin != null) gpsPincode = spotPin
                if (spotAddr != null) address = spotAddr
                if (spotCity != null) gpsCity = spotCity
                val stamped = withContext(Dispatchers.Default) {
                    runCatching {
                        val raw = decodeSampled(photoFile, 1600) ?: return@runCatching null
                        val rotated = applyExifRotation(photoFile, raw)
                        stampPhoto(rotated.copy(Bitmap.Config.ARGB_8888, true),
                            f?.lat ?: lat, f?.lng ?: lng, f?.acc ?: acc, spotAddr ?: address, agentName, caseLabel,
                            gThumb ?: mapThumb,
                            chosen?.label, spotPin ?: gpsPincode)
                    }.getOrNull()
                }
                if (stamped != null) photo = stamped
                stamping = false
            }
        }
    }
    val takePhoto = {
        val l = lastFix
        shot = if (l != null) Fix(l.latitude, l.longitude, l.accuracy.toDouble(), l.mockFlag() || mock, l.ageSeconds()) else null
        camera.launch(photoUri)
    }

    AlertDialog(
        onDismissRequest = { if (!submitting) onDismiss() },   // don't let a tap-outside cancel mid-submit
        title = { Text("Log field visit") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                submitError?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.labelMedium)
                }
                if (addresses.isNotEmpty()) {
                    Text("Which address are you visiting?", style = MaterialTheme.typography.labelSmall, color = Muted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        addresses.forEach { a ->
                            FilterChip(selected = slot == a.key, onClick = { slot = a.key }, label = { Text(a.label) })
                        }
                    }
                    chosen?.let { Text("📍 ${it.text}", style = MaterialTheme.typography.bodySmall) }
                }
                if (mock) Text("⚠ Fake-GPS / mock location app detected — this visit will be flagged to your team lead.",
                    color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelMedium)
                Text(
                    when {
                        lat == null -> "Getting GPS location…"
                        !goodFix -> "Getting accurate GPS… now ±${acc?.toInt() ?: "?"} m (need ±${GOOD_ACC_M.toInt()} m). Step outside / near a window."
                        address != null -> "GPS ±${acc?.toInt()} m ✓  $address"
                        else -> "GPS ±${acc?.toInt()} m ✓"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = if (lat != null && !goodFix) MaterialTheme.colorScheme.error else Muted,
                )
                if (BuildConfig.HAS_MAPS_KEY && lat != null) {
                    AndroidView(
                        factory = { ctx ->
                            MapView(ctx, GoogleMapOptions().liteMode(true).mapToolbarEnabled(false)).apply {
                                onCreate(null); onResume()
                                getMapAsync { gm -> gm.uiSettings.isMapToolbarEnabled = false; gMap = gm }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().height(130.dp),
                    )
                }
                Text("Outcome", style = MaterialTheme.typography.labelSmall, color = Muted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    dispositions.forEach { d ->
                        FilterChip(selected = disp == d, onClick = { disp = d }, label = { Text(d) })
                    }
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text("Payment collected"); Switch(checked = paid, onCheckedChange = { paid = it })
                }
                if (paid) OutlinedTextField(
                    value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text("Amount (₹)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (paid && isCreditCard) {
                    Text("Paid at (credit card)", style = MaterialTheme.typography.labelSmall, color = Muted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("STAB", "NORM").forEach { o ->
                            FilterChip(selected = normStab == o, onClick = { normStab = o }, label = { Text(o) })
                        }
                    }
                }
                // Promise-to-pay date — the visit re-surfaces the case on that day (rollover).
                if (!paid && disp == "PTP") {   // RTP = Refuse to Pay is not a promise
                    Text("PTP date (promised)", style = MaterialTheme.typography.labelSmall, color = Muted)
                    DatePickerField(label = "Pick date", iso = ptpDate, onPick = { ptpDate = it })
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text("Person has moved"); Switch(checked = moved, onCheckedChange = { moved = it })
                }
                OutlinedTextField(value = note, onValueChange = { note = it },
                    label = { Text("Note") }, modifier = Modifier.fillMaxWidth())

                photo?.let {
                    Image(it.asImageBitmap(), "Visit photo (geo-tagged)",
                        modifier = Modifier.fillMaxWidth().height(180.dp).padding(top = 4.dp))
                }
                OutlinedButton(onClick = { takePhoto() }, enabled = (goodFix || override) && !stamping,
                    modifier = Modifier.fillMaxWidth()) {
                    Text(
                        when {
                            stamping -> "Stamping location…"
                            !goodFix && !override -> "📷 Waiting for accurate GPS…"
                            photo == null -> "📷 Take geo-tagged photo"
                            else -> "Retake photo"
                        }
                    )
                }
                if (!goodFix && !override && photo == null) TextButton(onClick = { override = true }) {
                    Text("Take photo anyway (weak GPS — may be flagged)")
                }

                // Payment screenshot from the customer (optional) — saved with the visit and shared to WhatsApp.
                paymentPhoto?.let {
                    Image(it.asImageBitmap(), "Payment screenshot",
                        modifier = Modifier.fillMaxWidth().height(180.dp).padding(top = 4.dp))
                }
                Text(if (paymentPhoto == null) "🧾 Payment screenshot (optional)" else "🧾 Payment screenshot ✓",
                    style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { paymentPicker.launch("image/*") }, modifier = Modifier.weight(1f)) {
                        Text("🖼 Gallery")
                    }
                    OutlinedButton(onClick = { paymentCamera.launch(paymentPhotoUri) }, modifier = Modifier.weight(1f)) {
                        Text("📷 Camera")
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !submitting, onClick = {
                val jpeg = photo?.let { bmp ->
                    ByteArrayOutputStream().use { out -> bmp.compress(Bitmap.CompressFormat.JPEG, 85, out); out.toByteArray() }
                }
                val payJpeg = paymentPhoto?.let { bmp ->
                    ByteArrayOutputStream().use { out -> bmp.compress(Bitmap.CompressFormat.JPEG, 85, out); out.toByteArray() }
                }
                val draft = VisitDraft(
                    lat = lat, lng = lng, accuracy = acc,
                    personMoved = moved, paid = paid,
                    amount = amount.toDoubleOrNull() ?: 0.0,
                    disposition = disp, note = note.ifBlank { null }, photoJpeg = jpeg,
                    normStab = if (paid && isCreditCard) normStab else null,
                    ptpDate = if (!paid && disp == "PTP" && ptpDate.isNotBlank()) ptpDate else null,
                    paymentPhotoJpeg = payJpeg,
                    addressSlot = if (addresses.isNotEmpty()) slot else null,
                    addressText = chosen?.text,
                    gpsMock = (shot?.mock ?: false) || mock,
                    gpsFixAgeS = shot?.ageS ?: lastFix?.ageSeconds(),
                    gpsPincode = gpsPincode,
                    gpsAddress = address,
                    gpsCity = gpsCity,
                ).let { d ->
                    // The visit's GPS = the reading frozen when the photo was taken (matches the stamp).
                    shot?.let { f -> if (photo != null) d.copy(lat = f.lat, lng = f.lng, accuracy = f.acc) else d } ?: d
                }
                scope.launch {
                    submitting = true; submitError = null
                    val err = onSubmit(draft)          // suspend upload; null only on a confirmed save
                    submitting = false
                    if (err == null) onDismiss()       // close only when the server confirmed it
                    else submitError = err             // show the real reason (locked / offline …); entry kept
                }
            }) { Text(if (submitting) "Saving…" else "Save visit") }
        },
        dismissButton = { TextButton(enabled = !submitting, onClick = onDismiss) { Text("Cancel") } },
    )
}
