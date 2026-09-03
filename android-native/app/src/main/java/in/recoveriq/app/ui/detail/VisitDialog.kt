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
)

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

/** Draw the translucent geo-stamp banner across the bottom of the photo. */
private fun stampPhoto(
    src: Bitmap, lat: Double?, lng: Double?, acc: Double?, address: String?,
    agentName: String?, caseLabel: String?, mapThumb: Bitmap?,
): Bitmap {
    val bmp = if (src.isMutable) src else src.copy(Bitmap.Config.ARGB_8888, true)
    val c = Canvas(bmp)
    val w = bmp.width.toFloat()
    val h = bmp.height.toFloat()
    val scale = (w / 1080f).coerceAtLeast(0.5f)
    val pad = 20f * scale
    val big = 40f * scale
    val small = 32f * scale
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

    // Reserve a square on the right for the map thumbnail (if we fetched one).
    val mapSize = if (mapThumb != null) 300f * scale else 0f
    val mapGap = if (mapThumb != null) pad else 0f
    val textW = w - pad * 2 - edge - mapSize - mapGap

    // Build the lines from whatever data is available.
    val body = ArrayList<String>()
    agentName?.takeIf { it.isNotBlank() }?.let { body.addAll(wrap(paintBody, "Agent: $it", textW, 1)) }
    caseLabel?.takeIf { it.isNotBlank() }?.let { body.addAll(wrap(paintBody, it, textW, 1)) }
    address?.trim()?.takeIf { it.isNotEmpty() }?.let { body.addAll(wrap(paintBody, it, textW, 2)) }
    if (lat != null && lng != null) {
        body.add("Lat ${"%.6f".format(lat)}   Lng ${"%.6f".format(lng)}")
        body.add("GPS location" + (acc?.let { "  ±${it.toInt()} m" } ?: ""))
    } else {
        body.add("Location unavailable")
    }
    body.add(stamp)

    val lineGap = 1.28f
    val textBlockH = pad * 2 + big * lineGap + small * lineGap * body.size
    // Grow the panel so the map thumbnail always fits inside it.
    val panelH = maxOf(textBlockH, mapSize + pad * 2)
    val top = h - panelH

    // Dark scrim + blue accent edge.
    c.drawRect(0f, top, w, h, Paint().apply { color = Color.argb(160, 0, 0, 0) })
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
        c.drawText(ln, pad + edge, y, paintBody)
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
    onDismiss: () -> Unit,
    onSubmit: suspend (VisitDraft) -> Boolean,
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
    var lat by remember { mutableStateOf<Double?>(null) }
    var lng by remember { mutableStateOf<Double?>(null) }
    var acc by remember { mutableStateOf<Double?>(null) }
    var address by remember { mutableStateOf<String?>(null) }
    var mapThumb by remember { mutableStateOf<Bitmap?>(null) }

    // A private cache file the camera writes the full-res photo into, shared via FileProvider.
    val photoFile = remember { File(context.cacheDir, "visit_${System.currentTimeMillis()}.jpg") }
    val photoUri: Uri = remember {
        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", photoFile)
    }

    // Grab a fresh, high-accuracy fix when the dialog opens, then reverse-geocode to an address.
    androidx.compose.runtime.LaunchedEffect(Unit) {
        val fused = LocationServices.getFusedLocationProviderClient(context)
        runCatching {
            fused.lastLocation.addOnSuccessListener { loc ->
                if (loc != null && lat == null) { lat = loc.latitude; lng = loc.longitude; acc = loc.accuracy.toDouble() }
            }
        }
        runCatching {
            fused.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, null)
                .addOnSuccessListener { loc ->
                    if (loc != null) {
                        lat = loc.latitude; lng = loc.longitude; acc = loc.accuracy.toDouble()
                        scope.launch(Dispatchers.IO) {
                            val a = runCatching {
                                @Suppress("DEPRECATION")
                                Geocoder(context, Locale.ENGLISH)
                                    .getFromLocation(loc.latitude, loc.longitude, 1)
                                    ?.firstOrNull()
                                    ?.let { it.getAddressLine(0) ?: listOfNotNull(it.subLocality, it.locality, it.adminArea).joinToString(", ") }
                            }.getOrNull()
                            if (!a.isNullOrBlank()) withContext(Dispatchers.Main) { address = a }
                        }
                        scope.launch(Dispatchers.IO) {
                            val m = fetchMapThumb(loc.latitude, loc.longitude)
                            if (m != null) withContext(Dispatchers.Main) { mapThumb = m }
                        }
                    }
                }
        }
    }

    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        if (ok) {
            stamping = true
            scope.launch(Dispatchers.Default) {
                val stamped = runCatching {
                    val raw = decodeSampled(photoFile, 1600) ?: return@runCatching null
                    val rotated = applyExifRotation(photoFile, raw)
                    stampPhoto(rotated.copy(Bitmap.Config.ARGB_8888, true),
                        lat, lng, acc, address, agentName, caseLabel, mapThumb)
                }.getOrNull()
                withContext(Dispatchers.Main) { if (stamped != null) photo = stamped; stamping = false }
            }
        }
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
                Text(
                    when {
                        lat == null -> "Getting current location…"
                        address != null -> "Location ✓  $address"
                        else -> "Location captured ✓"
                    },
                    style = MaterialTheme.typography.labelSmall, color = Muted,
                )
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
                OutlinedButton(onClick = { camera.launch(photoUri) }, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        when {
                            stamping -> "Stamping location…"
                            photo == null -> "📷 Take geo-tagged photo"
                            else -> "Retake photo"
                        }
                    )
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !submitting, onClick = {
                val jpeg = photo?.let { bmp ->
                    ByteArrayOutputStream().use { out -> bmp.compress(Bitmap.CompressFormat.JPEG, 85, out); out.toByteArray() }
                }
                val draft = VisitDraft(
                    lat = lat, lng = lng, accuracy = acc,
                    personMoved = moved, paid = paid,
                    amount = amount.toDoubleOrNull() ?: 0.0,
                    disposition = disp, note = note.ifBlank { null }, photoJpeg = jpeg,
                    normStab = if (paid && isCreditCard) normStab else null,
                    ptpDate = if (!paid && disp == "PTP" && ptpDate.isNotBlank()) ptpDate else null,
                )
                scope.launch {
                    submitting = true; submitError = null
                    val ok = onSubmit(draft)          // suspend upload; true only on a confirmed save
                    submitting = false
                    if (ok) onDismiss()                // close only when the server confirmed it
                    else submitError = "Couldn't submit — check your signal and tap Save again. Your entry is kept."
                }
            }) { Text(if (submitting) "Saving…" else "Save visit") }
        },
        dismissButton = { TextButton(enabled = !submitting, onClick = onDismiss) { Text("Cancel") } },
    )
}
