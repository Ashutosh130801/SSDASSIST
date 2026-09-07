package `in`.recoveriq.app.ui.attendance

import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationManager
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.AttRow
import `in`.recoveriq.app.data.AttPresence
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.rememberLiveKey
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.Warn
import androidx.compose.ui.graphics.Color
import kotlinx.coroutines.delay

private fun fmtDur(sec: Int): String {
    val s = maxOf(0, sec); val h = s / 3600; val m = (s % 3600) / 60
    return if (h > 0) "${h}h ${m}m" else "${m}m"
}

// API timestamps are UTC (naive on SQLite). Treat as UTC and render in IST.
private fun hhmm(iso: String?): String {
    if (iso.isNullOrBlank()) return "—"
    return try {
        val core = iso.substringBefore('+').substringBefore('Z').replace('T', ' ').take(19)
        val pat = if (core.length > 10) "yyyy-MM-dd HH:mm:ss" else "yyyy-MM-dd HH:mm"
        val inFmt = java.text.SimpleDateFormat(pat, java.util.Locale.US)
        inFmt.timeZone = java.util.TimeZone.getTimeZone("UTC")
        val d = inFmt.parse(core.take(pat.length)) ?: return "—"
        val out = java.text.SimpleDateFormat("hh:mm a", java.util.Locale.US)
        out.timeZone = java.util.TimeZone.getTimeZone("Asia/Kolkata")
        out.format(d)
    } catch (e: Exception) { "—" }
}

private fun money(v: Double) = "₹" + "%,.0f".format(v)

/** Save the monthly attendance .xlsx to the cache and open/share it via the app's FileProvider. */
private suspend fun downloadAttendanceSheet(ctx: Context, vm: AuthViewModel, month: String, role: String) {
    try {
        val body = vm.repo.attDownload(month, role)
        val file = java.io.File(ctx.cacheDir, "Attendance_$month.xlsx")
        file.outputStream().use { out -> body.byteStream().use { it.copyTo(out) } }
        val uri = androidx.core.content.FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", file)
        val mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        val open = android.content.Intent(android.content.Intent.ACTION_VIEW)
            .setDataAndType(uri, mime)
            .addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            ctx.startActivity(open)
        } catch (e: Exception) {
            val share = android.content.Intent(android.content.Intent.ACTION_SEND)
                .setType(mime).putExtra(android.content.Intent.EXTRA_STREAM, uri)
                .addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
            ctx.startActivity(android.content.Intent.createChooser(share, "Attendance sheet").addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    } catch (e: Exception) { /* ignored — usually no viewer / permission */ }
}

/** Burn the GPS + name + timestamp onto the check-in photo (bottom strip) and return JPEG bytes. */
private fun stampCheckinPhoto(file: java.io.File, lat: Double?, lng: Double?, name: String): ByteArray? {
    val bmp0 = runCatching { android.graphics.BitmapFactory.decodeFile(file.absolutePath) }.getOrNull() ?: return null
    val maxW = 1280
    val bmp = if (bmp0.width > maxW)
        android.graphics.Bitmap.createScaledBitmap(bmp0, maxW, bmp0.height * maxW / bmp0.width, true) else bmp0
    val out = bmp.copy(android.graphics.Bitmap.Config.ARGB_8888, true)
    val c = android.graphics.Canvas(out)
    val w = out.width.toFloat(); val h = out.height.toFloat()
    val ts = w * 0.032f
    val bg = android.graphics.Paint().apply { color = 0xAA000000.toInt() }
    val tp = android.graphics.Paint().apply { color = 0xFFFFFFFF.toInt(); textSize = ts; isAntiAlias = true }
    val lines = listOf(
        name,
        if (lat != null && lng != null) "GPS ${"%.5f".format(lat)}, ${"%.5f".format(lng)}" else "GPS unavailable",
        java.text.SimpleDateFormat("dd MMM yyyy  HH:mm", java.util.Locale.ENGLISH).format(java.util.Date()),
    )
    val boxH = ts * (lines.size + 0.9f)
    c.drawRect(0f, h - boxH, w, h, bg)
    var y = h - boxH + ts
    for (ln in lines) { c.drawText(ln, w * 0.02f, y, tp); y += ts * 1.25f }
    val baos = java.io.ByteArrayOutputStream()
    out.compress(android.graphics.Bitmap.CompressFormat.JPEG, 85, baos)
    return baos.toByteArray()
}

/** Turn a failed check-in into a human message — surfaces the server's `detail` (e.g. "Photo too
 *  large", "After work hours") or a network hint, instead of silently re-showing the dialog. */
private fun checkinErrMsg(t: Throwable?): String = when (t) {
    is retrofit2.HttpException -> {
        val body = runCatching { t.response()?.errorBody()?.string() }.getOrNull()
        val detail = body?.let { runCatching { org.json.JSONObject(it).optString("detail") }.getOrNull() }
            ?.takeIf { it.isNotBlank() }
        detail ?: "Couldn't check in (error ${t.code()}). Please try again."
    }
    is java.io.IOException -> "Network problem — check your connection and try again."
    null -> "Couldn't check in. Please try again."
    else -> t.message ?: "Couldn't check in. Please try again."
}

@SuppressLint("MissingPermission")
private fun lastKnownLatLng(ctx: Context): Pair<Double, Double>? {
    return try {
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        for (p in listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)) {
            val l = lm.getLastKnownLocation(p)
            if (l != null) return l.latitude to l.longitude
        }
        null
    } catch (e: Exception) { null }
}

private fun presenceColor(state: String): Color = when (state) {
    "active" -> Good; "idle" -> Warn; else -> MutedDim
}

@Composable
fun PresenceChip(p: AttPresence) {
    val c = presenceColor(p.state)
    val plat = if (p.platform == "android") "mobile" else "web"
    val label = when (p.state) {
        "active" -> "Active on $plat"
        "idle" -> "Idle" + (if (p.idleSeconds > 60) " " + fmtDur(p.idleSeconds) else "")
        else -> "Offline"
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        Surface(color = c, shape = CircleShape, modifier = Modifier.size(8.dp)) {}
        Text(label, color = c, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
    }
}

/**
 * Runs the daily check-in gate + presence heartbeat + shift-end prompt. Mount once at the app root.
 */
@Composable
fun AttendanceGate(vm: AuthViewModel, user: User) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var me by remember { mutableStateOf<`in`.recoveriq.app.data.MeToday?>(null) }
    var showCheckin by remember { mutableStateOf(false) }
    var showOvertime by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var checkinErr by remember { mutableStateOf<String?>(null) }
    val isFos = user.role == "fos"
    var photoBytes by remember { mutableStateOf<ByteArray?>(null) }
    var photoLoc by remember { mutableStateOf<Pair<Double, Double>?>(null) }
    val camFile = remember { java.io.File(ctx.cacheDir, "checkin_cam.jpg") }
    val camUri = remember { androidx.core.content.FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", camFile) }
    val camLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.TakePicture()) { ok ->
        if (ok) scope.launch {
            val loc = lastKnownLatLng(ctx); photoLoc = loc
            photoBytes = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) {
                stampCheckinPhoto(camFile, loc?.first, loc?.second, user.name)
            }
        }
    }

    suspend fun reload() {
        me = runCatching { vm.repo.attMeToday() }.getOrNull()
        if (me?.needsCheckin == true) showCheckin = true
    }
    LaunchedEffect(Unit) { reload() }

    // Heartbeat every 30s while the app is in the foreground (composition alive).
    LaunchedEffect(me?.tracked) {
        if (me?.tracked != true) return@LaunchedEffect
        while (true) {
            val r = runCatching { vm.repo.attHeartbeat(active = true) }.getOrNull()
            if (r?.autoLogout == true) { vm.logout(); break }
            if (r?.promptOvertime == true) showOvertime = true
            delay(30_000)
        }
    }

    if (showCheckin && me?.needsCheckin == true) {
        val m = me!!
        AlertDialog(
            onDismissRequest = { showCheckin = false },
            title = { Text("Check in") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Good day, ${user.name.substringBefore(' ')}! Check in to start.",
                        style = MaterialTheme.typography.bodyMedium)
                    Text("Shift ${m.shiftStart}–${m.shiftEnd}. Your time and location are recorded.",
                        color = Muted, style = MaterialTheme.typography.labelSmall)
                    if (isFos) {
                        OutlinedButton(onClick = { runCatching { camLauncher.launch(camUri) } }) {
                            Text(if (photoBytes != null) "✓ Photo captured · retake" else "📷 Take check-in photo")
                        }
                        if (photoBytes == null) Text("A GPS-tagged check-in photo is required.",
                            color = Warn, style = MaterialTheme.typography.labelSmall)
                    }
                    if (checkinErr != null) Text(checkinErr!!, color = Warn,
                        style = MaterialTheme.typography.labelSmall)
                }
            },
            confirmButton = {
                Button(enabled = !busy && (!isFos || photoBytes != null), onClick = {
                    busy = true; checkinErr = null
                    scope.launch {
                        val res = if (isFos && photoBytes != null) {
                            runCatching { vm.repo.attCheckinPhoto(photoBytes!!, photoLoc?.first, photoLoc?.second) }
                        } else {
                            val loc = lastKnownLatLng(ctx)
                            runCatching { vm.repo.attCheckin(loc?.first, loc?.second) }
                        }
                        busy = false
                        if (res.isSuccess) {
                            // Trust the check-in response — close and refresh once. Do NOT re-derive
                            // "needs check-in" from a follow-up read (that was the loop).
                            showCheckin = false; photoBytes = null; checkinErr = null
                            me = runCatching { vm.repo.attMeToday() }.getOrNull()
                        } else {
                            // Keep the dialog open WITH the real reason instead of silently flashing back.
                            checkinErr = checkinErrMsg(res.exceptionOrNull())
                        }
                    }
                }) { Text(if (busy) "Checking in…" else if (isFos) "Check in with photo" else "Check in") }
            },
            dismissButton = { TextButton(onClick = { showCheckin = false }) { Text("Not now") } },
        )
    }

    if (showOvertime) {
        AlertDialog(
            onDismissRequest = { showOvertime = false },
            title = { Text("Shift ended (${me?.shiftEnd ?: "19:00"})") },
            text = { Text("Check out for the day, or continue working (overtime)? You'll be auto checked-out in 5 minutes if there's no response.") },
            confirmButton = {
                Button(onClick = {
                    showOvertime = false
                    scope.launch { runCatching { vm.repo.attOvertime() } }
                }) { Text("Continue working") }
            },
            dismissButton = {
                OutlinedButton(onClick = {
                    showOvertime = false
                    scope.launch {
                        val loc = lastKnownLatLng(ctx)
                        runCatching { vm.repo.attCheckout(loc?.first, loc?.second) }
                        vm.logout()
                    }
                }) { Text("Check out") }
            },
        )
    }
}

@Suppress("UNCHECKED_CAST")
private fun Any?.rowsOf(): List<Map<String, Any?>> =
    (this as? List<*>)?.mapNotNull { it as? Map<String, Any?> } ?: emptyList()

@Suppress("UNCHECKED_CAST")
private fun Any?.mapOf2(): Map<String, Any?> = (this as? Map<String, Any?>) ?: emptyMap()

private fun Any?.i(): Int = (this as? Number)?.toInt() ?: 0
private fun letterColor(v: String): Color = when (v) {
    "P" -> Good; "L" -> Warn; "LV" -> BrandBlue; "A" -> Color(0xFFDC2626); "W" -> MutedDim; else -> MutedDim
}

/** Attendance dashboard — today's board + monthly matrix. */
@Composable
fun AttendanceScreen(vm: AuthViewModel, user: User) {
    var tab by remember { mutableStateOf("day") }
    var role by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    val live = rememberLiveKey()
    val ctx = LocalContext.current
    val dlScope = rememberCoroutineScope()
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SectionTitle("Attendance", Modifier.padding(top = 12.dp, start = 4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip(selected = tab == "day", onClick = { tab = "day" }, label = { Text("Today") })
            FilterChip(selected = tab == "month", onClick = { tab = "month" }, label = { Text("This month") })
        }
        if (tab == "month") {
            AsyncContent(key = "attm|$role|$live", block = { vm.repo.attMonth(null, role) }) { m, _ ->
                val days = (m["days"] as? List<*>)?.map { it.toString() } ?: emptyList()
                val people = m["people"].rowsOf().filter {
                    q.isBlank() || (it["name"]?.toString() ?: "").contains(q, true) ||
                        (it["emp_code"]?.toString() ?: "").contains(q, true)
                }
                OutlinedTextField(value = q, onValueChange = { q = it }, singleLine = true,
                    label = { Text("Search name / ID") }, modifier = Modifier.fillMaxWidth())
                if (m["can_download"] == true) {
                    val mm = m["month"]?.toString() ?: ""
                    Button(onClick = { dlScope.launch { downloadAttendanceSheet(ctx, vm, mm, role) } }) {
                        Text("⬇ Download sheet (.xlsx)")
                    }
                }
                Row(Modifier.horizontalScroll(rememberScrollState())) {
                    Column {
                        // header
                        Row {
                            Text("Name", Modifier.width(120.dp), fontWeight = FontWeight.Bold,
                                color = BrandBlue, style = MaterialTheme.typography.labelSmall)
                            days.forEach { d -> Text(d.takeLast(2), Modifier.width(22.dp),
                                fontWeight = FontWeight.Bold, color = Muted, style = MaterialTheme.typography.labelSmall) }
                            listOf("P", "L", "LV", "A", "Hrs").forEach { h -> Text(h, Modifier.width(34.dp),
                                fontWeight = FontWeight.Bold, color = BrandBlue, style = MaterialTheme.typography.labelSmall) }
                        }
                        people.forEach { p ->
                            val pd = p["days"].mapOf2()
                            Row(Modifier.padding(vertical = 2.dp)) {
                                Text(p["name"]?.toString() ?: "—", Modifier.width(120.dp),
                                    style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Medium)
                                days.forEach { d ->
                                    val v = pd[d]?.toString() ?: ""
                                    Text(v, Modifier.width(22.dp), color = letterColor(v),
                                        fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
                                }
                                Text("${p["present"].i()}", Modifier.width(34.dp), style = MaterialTheme.typography.labelSmall)
                                Text("${p["late"].i()}", Modifier.width(34.dp), color = Warn, style = MaterialTheme.typography.labelSmall)
                                Text("${p["leave"].i()}", Modifier.width(34.dp), color = BrandBlue, style = MaterialTheme.typography.labelSmall)
                                Text("${p["absent"].i()}", Modifier.width(34.dp), color = Color(0xFFDC2626), style = MaterialTheme.typography.labelSmall)
                                Text("${(p["worked_hours"] as? Number)?.toDouble() ?: 0.0}", Modifier.width(34.dp), style = MaterialTheme.typography.labelSmall)
                            }
                        }
                    }
                }
                Text("P Present · L Late · LV Leave · A Absent · W Week-off. Download the full sheet from the web app.",
                    color = Muted, style = MaterialTheme.typography.labelSmall)
            }
            return@Column
        }
        AsyncContent(key = "att|$role|$live", block = { vm.repo.attDay(null, role) }) { d, _ ->
            val roles = d.rows.map { it.role ?: "" }.filter { it.isNotBlank() }.distinct().sorted()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Present", d.summary.present.toString(), Good, Modifier.weight(1f))
                Kpi("Late", d.summary.late.toString(), Warn, Modifier.weight(1f))
                Kpi("Absent", d.summary.absent.toString(), Color(0xFFDC2626), Modifier.weight(1f))
                Kpi("Online", d.summary.online.toString(), BrandBlue, Modifier.weight(1f))
            }
            OutlinedTextField(value = q, onValueChange = { q = it }, singleLine = true,
                label = { Text("Search name / ID") }, modifier = Modifier.fillMaxWidth())
            if (roles.isNotEmpty()) {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(selected = role.isBlank(), onClick = { role = "" }, label = { Text("All") })
                    roles.forEach { r -> FilterChip(selected = role == r, onClick = { role = r }, label = { Text(r) }) }
                }
            }
            val rows = d.rows.filter {
                q.isBlank() || (it.name ?: "").contains(q, true) || (it.empCode ?: "").contains(q, true)
            }
            rows.forEach { AttCard(it) }
            if (rows.isEmpty()) Text("No one to show.", color = Muted, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun Kpi(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    InfoCard(modifier) {
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = color)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Muted)
    }
}

private fun openMap(ctx: Context, lat: Double, lng: Double) {
    try {
        val uri = android.net.Uri.parse("geo:$lat,$lng?q=$lat,$lng")
        ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, uri)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: Exception) {
        try {
            ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse("https://maps.google.com/?q=$lat,$lng"))
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: Exception) {}
    }
}

@Composable
private fun AttCard(r: AttRow) {
    val ctx = LocalContext.current
    val statusColor = when { r.late -> Warn; r.status == "present" -> Good; r.status == "leave" -> BrandBlue; r.status == "absent" -> Color(0xFFDC2626); else -> MutedDim }
    val statusText = if (r.late) "Present (late)" else (r.status.replaceFirstChar { it.uppercase() })
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(r.name ?: "—", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(r.empCode, r.role).joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall, color = Muted)
                PresenceChip(r.presence)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(statusText, color = statusColor, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelMedium)
                Text("In ${hhmm(r.checkInAt)} · Out ${hhmm(r.checkOutAt)}",
                    style = MaterialTheme.typography.labelSmall, color = Muted)
                Text("Worked ${fmtDur(r.workedSeconds)} · Idle ${fmtDur(r.idleSeconds)}",
                    style = MaterialTheme.typography.labelSmall, color = MutedDim)
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (r.showActivity) {
                val suffix = if (r.teamTotal) " (team)" else ""
                Text("📞 ${r.calls}$suffix", style = MaterialTheme.typography.labelSmall, color = Muted)
                Text("🧍 ${r.visits}", style = MaterialTheme.typography.labelSmall, color = Muted)
                Text("💰 ${money(r.collected)}", style = MaterialTheme.typography.labelSmall, color = Good)
            }
            if (r.checkInLat != null && r.checkInLng != null)
                Text("📍 ${"%.4f".format(r.checkInLat)}, ${"%.4f".format(r.checkInLng)}",
                    style = MaterialTheme.typography.labelSmall, color = BrandBlue,
                    modifier = Modifier.clickable { openMap(ctx, r.checkInLat, r.checkInLng) })
        }
        if (r.role == "fos" && r.liveLat != null && r.liveLng != null) {
            Text("🛰 Live · ${hhmm(r.liveAt)} · tap to track",
                style = MaterialTheme.typography.labelSmall, color = Good, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 2.dp).clickable { openMap(ctx, r.liveLat, r.liveLng) })
        }
    }
}
