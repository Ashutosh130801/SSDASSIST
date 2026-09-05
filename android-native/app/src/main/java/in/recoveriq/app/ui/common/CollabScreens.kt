package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Warn
import `in`.recoveriq.app.ui.theme.Bad
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// ---- tiny generic-map helpers (endpoints return Map<String, Any?>) ----
@Suppress("UNCHECKED_CAST")
private fun Any?.m(): Map<String, Any?> = this as? Map<String, Any?> ?: emptyMap()
@Suppress("UNCHECKED_CAST")
private fun Any?.l(): List<Any?> = this as? List<Any?> ?: emptyList()
private fun Any?.d(): Double = (this as? Number)?.toDouble() ?: 0.0
private fun Any?.i(): Int = (this as? Number)?.toInt() ?: 0
private fun Any?.s(): String = this?.toString() ?: ""
private fun rupee(v: Double) = "₹" + "%,.0f".format(v)

private fun roleLabel(r: String) = when (r) {
    "fos" -> "Field Agent"; "telecaller" -> "Tele-caller"; "teamlead" -> "Team Lead"
    "manager" -> "Manager"; "headoffice" -> "Head Office"; "backend" -> "Back Office"
    "hr" -> "HR"; "admin" -> "Admin"; else -> r.replaceFirstChar { it.uppercase() }
}

// WhatsApp-style short time for the chat list ("now", "9:41 AM", "Mon", "12 Aug").
private fun chatWhen(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    return try {
        val t = java.time.OffsetDateTime.parse(iso).toInstant().toEpochMilli()
        val now = System.currentTimeMillis()
        val mins = (now - t) / 60000
        when {
            mins < 1 -> "now"
            mins < 1440 && java.text.SimpleDateFormat("yyyyMMdd").format(java.util.Date(t)) ==
                java.text.SimpleDateFormat("yyyyMMdd").format(java.util.Date(now)) ->
                java.text.SimpleDateFormat("h:mm a").format(java.util.Date(t))
            mins < 10080 -> java.text.SimpleDateFormat("EEE").format(java.util.Date(t))
            else -> java.text.SimpleDateFormat("d MMM").format(java.util.Date(t))
        }
    } catch (_: Exception) { "" }
}

private val MONTHS = listOf("current" to "This month", "next" to "Next", "last" to "Last", "all" to "All")

@Composable
private fun Kpi(label: String, value: String, color: Color = TextDark) {
    Card(colors = CardDefaults.cardColors(containerColor = CardWhite),
        modifier = Modifier.width(120.dp)) {
        Column(Modifier.padding(10.dp)) {
            Text(label, color = Muted, fontSize = 11.sp)
            Text(value, color = color, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }
    }
}

/* ============================ RTSB ============================ */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RtsbScreen(vm: AuthViewModel, user: User) {
    var mb by remember { mutableStateOf("current") }
    var role by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf("pending") }
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("🎯 RTSB — target vs achievement", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = TextDark)
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            MONTHS.forEach { (v, lbl) -> FilterChip(selected = mb == v, onClick = { mb = v }, label = { Text(lbl) }) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("" to "All", "caller" to "Callers", "fos" to "Field").forEach { (v, lbl) ->
                FilterChip(selected = role == v, onClick = { role = v }, label = { Text(lbl) })
            }
        }
        Spacer(Modifier.height(6.dp))
        AsyncContent(key = "$mb|$role", block = { vm.repo.rtsb(mb, role) }) { d, _ ->
            val t = d["totals"].m()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("People", t["people"].i().toString())
                Kpi("Achieved", t["achieved"].i().toString(), Good)
                Kpi("Not yet", t["pending"].i().toString(), Warn)
            }
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("pending" to "Not achieved", "achieved" to "Achieved", "all" to "All").forEach { (v, lbl) ->
                    FilterChip(selected = tab == v, onClick = { tab = v }, label = { Text(lbl) })
                }
            }
            val list = when (tab) {
                "achieved" -> d["achieved_list"].l(); "all" -> d["people"].l(); else -> d["pending_list"].l()
            }
            LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(list) { row ->
                    val p = row.m()
                    Card(colors = CardDefaults.cardColors(containerColor = CardWhite)) {
                        Column(Modifier.padding(10.dp)) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("${p["name"].s()}  ", fontWeight = FontWeight.SemiBold, color = TextDark)
                                Text("${p["pct_done"].d()}%", fontWeight = FontWeight.Bold,
                                    color = if (p["achieved"] == true) Good else if (p["pct_done"].d() >= 60) Warn else Bad)
                            }
                            Text("${if (p["role"].s() == "fos") "Field" else "Caller"} · ${p["paid"].i()}/${p["cases"].i()} paid · " +
                                "target ${rupee(p["target_enr"].d())} · got ${rupee(p["achieved_enr"].d())} · gap ${rupee(p["gap_enr"].d())}",
                                color = Muted, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

/* ============================ To-Do / Work Queue ============================ */
@Composable
fun TodoScreen(vm: AuthViewModel, user: User, onOpenCase: (Int) -> Unit) {
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("📋 My work queue — today", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = TextDark)
        AsyncContent(block = { vm.repo.todoMe() }) { d, _ ->
            val isFos = user.role == "fos"
            val sections = listOf(
                Triple("ptp_broken", "🔴 Broken PTPs (overdue)", Bad),
                Triple("ptp_today", "🤝 Today's PTPs", Warn),
                if (isFos) Triple("visits_pending", "📍 Visits pending", BrandBlue)
                else Triple("calls_pending", "📞 Calls pending", BrandBlue),
                Triple("paid_not_updated", "💰 Paid — status not updated", Good),
            )
            val callbacks = d["callbacks"].l()
            LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (callbacks.isNotEmpty()) item {
                    Card(colors = CardDefaults.cardColors(containerColor = CardWhite)) {
                        Column(Modifier.padding(10.dp)) {
                            Text("📞 Callback requests (${callbacks.size})", fontWeight = FontWeight.Bold, color = BrandBlue)
                            callbacks.forEach { cb -> val c = cb.m()
                                Text("${c["from"].s()} · ${c["body"].s()}", fontSize = 12.sp, color = TextDark,
                                    modifier = Modifier.padding(top = 3.dp).clickable { (c["case_id"] as? Number)?.let { onOpenCase(it.toInt()) } })
                            }
                        }
                    }
                }
                sections.forEach { (key, label, color) ->
                    val rows = d[key].l()
                    item {
                        Card(colors = CardDefaults.cardColors(containerColor = CardWhite)) {
                            Column(Modifier.padding(10.dp)) {
                                Text("$label · ${rows.size}", fontWeight = FontWeight.SemiBold, color = color)
                                if (rows.isEmpty()) Text("Nothing pending 🎉", color = Muted, fontSize = 12.sp)
                                else rows.take(40).forEach { rr -> val c = rr.m()
                                    Column(Modifier.fillMaxWidth().padding(top = 5.dp)
                                        .clickable { (c["id"] as? Number)?.let { onOpenCase(it.toInt()) } }) {
                                        Text("${c["customer"].s().ifBlank { c["account"].s() }}", color = TextDark, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                                        Text("${c["bank"].s()} ${c["product"].s()} · pending ${rupee(c["pending"].d())}" +
                                            (c["follow_up"]?.let { " · due ${it.s()}" } ?: ""), color = Muted, fontSize = 11.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/* ============================ Live Monitor ============================ */
@Composable
fun MonitorScreen(vm: AuthViewModel, user: User) {
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { while (true) { delay(15000); tick++ } }
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("🖥️ Live Monitor  ·  updates every 15s", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = TextDark)
        AsyncContent(key = tick, block = { vm.repo.monitorLive() }) { d, _ ->
            val c = d["counters"].m()
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Online", c["online_now"].i().toString(), Good)
                Kpi("Calls", c["calls"].i().toString())
                Kpi("Visits", c["visits"].i().toString())
                Kpi("Collected", rupee(c["collected"].d()), Good)
            }
            val feed = d["feed"].l()
            LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (feed.isEmpty()) item { Text("No activity yet today.", color = Muted, fontSize = 12.sp) }
                items(feed) { ff -> val f = ff.m()
                    Card(colors = CardDefaults.cardColors(containerColor = CardWhite)) {
                        Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Text(if (f["type"].s() == "call") "📞" else "📍")
                            Text(f["who"].s(), fontWeight = FontWeight.SemiBold, color = TextDark, modifier = Modifier.weight(1f))
                            Text(f["detail"].s(), color = BrandBlue, fontSize = 12.sp)
                            if (f["amount"].d() > 0) Text(rupee(f["amount"].d()), color = Good, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

/* ============================ FOS "Request callback" button ============================ */
@Composable
fun RequestCallbackButton(vm: AuthViewModel, caseId: Int, hasCaller: Boolean) {
    if (!hasCaller) return
    val scope = rememberCoroutineScope()
    var sent by remember { mutableStateOf(false) }
    OutlinedButton(onClick = {
        scope.launch { try { vm.repo.chatCallback(caseId, null); sent = true } catch (_: Exception) {} }
    }, enabled = !sent) { Text(if (sent) "✓ Callback requested" else "📞 Request callback") }
}

/* ============================ Floating Chat widget ============================ */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatFab(vm: AuthViewModel, user: User, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var unread by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { while (true) { try { unread = vm.repo.chatUnread() } catch (_: Exception) {}; delay(15000) } }

    Box(modifier) {
        BadgedBox(badge = { if (unread > 0) Badge { Text(unread.toString()) } }) {
            FloatingActionButton(onClick = { open = true }, containerColor = BrandBlue, contentColor = Color.White) {
                Text("💬", fontSize = 20.sp)
            }
        }
    }
    if (open) {
        val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        ModalBottomSheet(onDismissRequest = { open = false }, sheetState = sheet, containerColor = CardWhite) {
            ChatPanel(vm, user) { open = false; scope.launch { try { unread = vm.repo.chatUnread() } catch (_: Exception) {} } }
        }
    }
}

// WhatsApp palette — kept local so the chat looks like WhatsApp regardless of the app's blue theme.
private val WaHeader = Color(0xFF008069)
private val WaTeal = Color(0xFF075E54)
private val WaOut = Color(0xFFD9FDD3)
private val WaBg = Color(0xFFEFEAE2)

@Composable
private fun Avatar(name: String, office: Boolean = false, small: Boolean = false) {
    val sz = if (small) 34.dp else 44.dp
    Box(Modifier.size(sz).background(if (office) WaTeal else Color(0xFFDFE5E7), CircleShape),
        contentAlignment = Alignment.Center) {
        Text(if (office) "🏢" else name.trim().take(1).uppercase().ifBlank { "?" },
            color = if (office) Color.White else Color(0xFF5B6B72), fontWeight = FontWeight.Bold,
            fontSize = if (small) 15.sp else 18.sp)
    }
}

@Composable
private fun ConvRow(name: String, office: Boolean, last: String, at: String?, unread: Int, sub: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Avatar(name, office = office); Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(name, fontWeight = FontWeight.SemiBold, color = Color(0xFF111B21), maxLines = 1)
                if (!at.isNullOrBlank()) Text(chatWhen(at), color = if (unread > 0) WaHeader else Muted,
                    fontSize = 10.sp, fontWeight = if (unread > 0) FontWeight.Bold else FontWeight.Normal)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Text(last.ifBlank { sub }, color = Muted, fontSize = 12.5.sp, maxLines = 1, modifier = Modifier.weight(1f))
                if (unread > 0) Box(Modifier.background(Color(0xFF25D366), CircleShape).padding(horizontal = 6.dp, vertical = 1.dp)) {
                    Text(unread.toString(), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun ChatPanel(vm: AuthViewModel, user: User, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    var active by remember { mutableStateOf<Pair<Int?, Boolean>?>(null) }
    var activeName by remember { mutableStateOf("") }
    var activeRole by remember { mutableStateOf("") }
    var picker by remember { mutableStateOf(false) }
    var bcast by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }   // conversation-list search
    var pq by remember { mutableStateOf("") }       // picker search
    var roleF by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }         // bump to refetch contacts
    var bsel by remember { mutableStateOf(setOf<Int>()) }   // broadcast recipients
    var btext by remember { mutableStateOf("") }
    var bq by remember { mutableStateOf("") }
    val canBroadcast = user.role in setOf("admin", "manager", "headoffice", "teamlead", "backend", "hr")
    val open: (Int?, Boolean, String, String) -> Unit = { id, off, nm, rl ->
        active = id to off; activeName = nm; activeRole = rl; picker = false; bcast = false
    }
    val requestChat: (Int) -> Unit = { id ->
        scope.launch { runCatching { vm.repo.chatRequest(id) }; reload++ }
    }
    Column(Modifier.fillMaxWidth().height(560.dp)) {
        when {
            // ================= THREAD =================
            active != null -> {
                Row(Modifier.fillMaxWidth().background(WaHeader).padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("‹", color = Color.White, fontSize = 24.sp, modifier = Modifier.clickable { active = null })
                    Spacer(Modifier.width(8.dp)); Avatar(activeName, office = active!!.second, small = true)
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(activeName, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp, maxLines = 1)
                        Text(activeRole, color = Color.White.copy(alpha = 0.85f), fontSize = 10.5.sp, maxLines = 1)
                    }
                }
                ChatThread(vm, active!!.first, active!!.second)
            }
            // ================= NEW CHAT (picker) =================
            picker -> {
                Row(Modifier.fillMaxWidth().background(WaHeader).padding(horizontal = 10.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("‹", color = Color.White, fontSize = 24.sp, modifier = Modifier.clickable { picker = false; pq = ""; roleF = "" })
                    Spacer(Modifier.width(8.dp)); Text("Select contact", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                }
                OutlinedTextField(value = pq, onValueChange = { pq = it }, modifier = Modifier.fillMaxWidth().padding(8.dp),
                    placeholder = { Text("Search name or ID…") }, singleLine = true, leadingIcon = { Text("🔍") })
                AsyncContent(key = reload, block = { vm.repo.chatContacts() }) { d, _ ->
                    val contacts = d["contacts"].l().map { it.m() }
                    val roles = d["roles"].l().map { it.s() }
                    val office = d["office"].m()
                    val term = pq.trim().lowercase()
                    val list = contacts.filter { c ->
                        (roleF.isBlank() || c["role"].s() == roleF) &&
                            (term.isBlank() || c["name"].s().lowercase().contains(term) ||
                                c["emp_code"].s().lowercase().contains(term))
                    }
                    if (roles.isNotEmpty()) {
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            FilterChip(selected = roleF.isBlank(), onClick = { roleF = "" }, label = { Text("All") })
                            roles.forEach { r -> FilterChip(selected = roleF == r, onClick = { roleF = r }, label = { Text(roleLabel(r)) }) }
                        }
                        Spacer(Modifier.height(4.dp))
                    }
                    LazyColumn {
                        item { ConvRow("Office desk", true, office["last"].s(), null, 0, "Broadcast to the whole office") { open(null, true, "Office desk", "Office broadcast") } }
                        if (list.isEmpty()) item {
                            Text(if (term.isNotBlank() || roleF.isNotBlank()) "No one matches that search." else "No contacts in your scope yet.",
                                color = Muted, fontSize = 12.sp, modifier = Modifier.padding(14.dp))
                        }
                        items(list) { c ->
                            val locked = c["locked"] == true
                            val pend = c["pending"] == true
                            Row(Modifier.fillMaxWidth().clickable {
                                if (locked) { if (!pend) requestChat(c["id"].i()) } else open(c["id"].i(), false, c["name"].s(), roleLabel(c["role"].s()))
                            }.padding(horizontal = 14.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                                Avatar(c["name"].s()); Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(c["name"].s(), fontWeight = FontWeight.SemiBold, color = Color(0xFF111B21), maxLines = 1)
                                    Text(roleLabel(c["role"].s()) + (c["emp_code"].s().let { if (it.isNotBlank()) " · $it" else "" }),
                                        color = Muted, fontSize = 11.5.sp, maxLines = 1)
                                }
                                if (locked) Text(if (pend) "⏳ Requested" else "🔒 Request",
                                    color = if (pend) Warn else WaHeader, fontSize = 11.5.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
            // ================= BROADCAST (select many) =================
            bcast -> {
                Row(Modifier.fillMaxWidth().background(WaHeader).padding(horizontal = 10.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("‹", color = Color.White, fontSize = 24.sp, modifier = Modifier.clickable { bcast = false; bq = "" })
                    Spacer(Modifier.width(8.dp))
                    Text("📢 Broadcast" + (if (bsel.isNotEmpty()) " · ${bsel.size} selected" else ""),
                        color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                }
                OutlinedTextField(value = bq, onValueChange = { bq = it }, modifier = Modifier.fillMaxWidth().padding(8.dp),
                    placeholder = { Text("Search people…") }, singleLine = true, leadingIcon = { Text("🔍") })
                Box(Modifier.weight(1f).fillMaxWidth().background(WaBg)) {
                    AsyncContent(block = { vm.repo.chatContacts() }) { d, _ ->
                        val term = bq.trim().lowercase()
                        val list = d["contacts"].l().map { it.m() }.filter {
                            it["locked"] != true && (term.isBlank() || it["name"].s().lowercase().contains(term) || it["emp_code"].s().lowercase().contains(term))
                        }
                        LazyColumn(Modifier.fillMaxSize()) {
                            items(list) { c ->
                                val id = c["id"].i(); val on = bsel.contains(id)
                                Row(Modifier.fillMaxWidth().clickable { bsel = if (on) bsel - id else bsel + id }
                                    .background(if (on) Color(0x1400A884) else Color.Transparent)
                                    .padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                                    androidx.compose.material3.Checkbox(checked = on, onCheckedChange = { bsel = if (on) bsel - id else bsel + id })
                                    Spacer(Modifier.width(6.dp)); Avatar(c["name"].s(), small = true); Spacer(Modifier.width(10.dp))
                                    Column(Modifier.weight(1f)) {
                                        Text(c["name"].s(), fontWeight = FontWeight.SemiBold, color = Color(0xFF111B21), maxLines = 1)
                                        Text(roleLabel(c["role"].s()), color = Muted, fontSize = 11.sp, maxLines = 1)
                                    }
                                }
                            }
                        }
                    }
                }
                Column(Modifier.fillMaxWidth().background(Color(0xFFF0F2F5)).padding(8.dp)) {
                    OutlinedTextField(value = btext, onValueChange = { btext = it }, modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("Broadcast message…") }, maxLines = 3)
                    Spacer(Modifier.height(6.dp))
                    Button(onClick = {
                        val t = btext.trim(); val ids = bsel.toList()
                        if (t.isNotEmpty() && ids.isNotEmpty()) scope.launch {
                            runCatching { vm.repo.chatBroadcast(ids, t) }
                            bcast = false; bsel = emptySet(); btext = ""; bq = ""
                        }
                    }, enabled = btext.isNotBlank() && bsel.isNotEmpty(), modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = WaHeader)) {
                        Text("Send to ${bsel.size} ${if (bsel.size == 1) "person" else "people"}", color = Color.White)
                    }
                }
            }
            // ================= CHATS (conversation list) =================
            else -> {
                Row(Modifier.fillMaxWidth().background(WaHeader).padding(horizontal = 14.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("Chats", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.weight(1f))
                    if (canBroadcast) Text("📢", color = Color.White, fontSize = 17.sp,
                        modifier = Modifier.clickable { bcast = true }.padding(end = 14.dp))
                    Text("✕", color = Color.White, fontSize = 16.sp, modifier = Modifier.clickable { onClose() })
                }
                OutlinedTextField(value = query, onValueChange = { query = it }, modifier = Modifier.fillMaxWidth().padding(8.dp),
                    placeholder = { Text("Search chats") }, singleLine = true, leadingIcon = { Text("🔍") })
                Box(Modifier.weight(1f).fillMaxWidth().background(WaBg)) {
                    AsyncContent(block = { vm.repo.chatContacts() }) { d, _ ->
                        val contacts = d["contacts"].l().map { it.m() }
                        val office = d["office"].m()
                        val term = query.trim().lowercase()
                        val convos = contacts.filter { !(it["last_at"] as? String).isNullOrBlank() &&
                            (term.isBlank() || it["name"].s().lowercase().contains(term)) }
                        val hasOffice = !(office["last_at"] as? String).isNullOrBlank()
                        LazyColumn(Modifier.fillMaxSize()) {
                            if (hasOffice) item { ConvRow("Office desk", true, office["last"].s(), office["last_at"] as? String, 0, "Office broadcast") { open(null, true, "Office desk", "Office broadcast") } }
                            if (convos.isEmpty() && !hasOffice) item {
                                Text("No conversations yet.\nTap the pencil button to start a chat.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(20.dp))
                            }
                            items(convos) { c -> ConvRow(c["name"].s(), false, c["last"].s(), c["last_at"] as? String, c["unread"].i(), roleLabel(c["role"].s())) { open(c["id"].i(), false, c["name"].s(), roleLabel(c["role"].s())) } }
                        }
                    }
                    // New-chat FAB
                    FloatingActionButton(onClick = { picker = true }, containerColor = WaHeader, contentColor = Color.White,
                        modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) { Text("✎", fontSize = 22.sp) }
                }
            }
        }
    }
}

@Composable
private fun ChatThread(vm: AuthViewModel, withId: Int?, office: Boolean) {
    var text by remember { mutableStateOf("") }
    var tick by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(withId, office) { while (true) { delay(8000); tick++ } }
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth().background(WaBg)) {
            AsyncContent(key = "$withId|$office|$tick", block = { vm.repo.chatThread(withId, office) }) { d, _ ->
                val msgs = d["messages"].l()
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    if (msgs.isEmpty()) item {
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            Text("No messages yet. Say hello 👋", color = Color(0xFF667781), fontSize = 12.sp,
                                modifier = Modifier.background(Color.White, RoundedCornerShape(8.dp)).padding(horizontal = 12.dp, vertical = 5.dp))
                        }
                    }
                    items(msgs) { mm -> val m = mm.m(); val mine = m["mine"] == true
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
                            Box(Modifier.widthIn(max = 260.dp).background(if (mine) WaOut else Color.White, RoundedCornerShape(8.dp)).padding(horizontal = 9.dp, vertical = 5.dp)) {
                                Column {
                                    if (!mine && office) Text(m["from"].s(), fontSize = 10.5.sp, fontWeight = FontWeight.Bold, color = WaHeader)
                                    Text(m["body"].s(), color = Color(0xFF111B21), fontSize = 13.sp)
                                    if (mine) Text("✓✓", fontSize = 10.sp, fontWeight = FontWeight.Bold,
                                        color = if (m["read"] == true) Color(0xFF53BDEB) else Color(0xFF8696A0),
                                        modifier = Modifier.align(Alignment.End))
                                }
                            }
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().background(Color(0xFFF0F2F5)).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f),
                placeholder = { Text("Type a message") }, singleLine = true)
            Spacer(Modifier.width(6.dp))
            Box(Modifier.size(44.dp).background(WaHeader, CircleShape).clickable {
                val b = text.trim(); if (b.isNotEmpty()) { text = ""
                    val body: Map<String, Any?> = if (office) mapOf("office" to true, "body" to b) else mapOf("to_id" to withId, "body" to b)
                    scope.launch { try { vm.repo.chatSend(body); tick++ } catch (_: Exception) {} }
                }
            }, contentAlignment = Alignment.Center) { Text("➤", color = Color.White, fontSize = 17.sp) }
        }
    }
}
