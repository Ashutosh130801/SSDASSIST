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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
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

@Composable
private fun ChatPanel(vm: AuthViewModel, user: User, onClose: () -> Unit) {
    // active = Pair(id?, office)
    var active by remember { mutableStateOf<Pair<Int?, Boolean>?>(null) }
    var activeName by remember { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().height(480.dp).padding(12.dp)) {
        if (active == null) {
            Text("💬 Messages", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = TextDark)
            Spacer(Modifier.height(6.dp))
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFEFF3FF)),
                modifier = Modifier.fillMaxWidth().clickable { active = null to true; activeName = "Office desk" }) {
                Column(Modifier.padding(12.dp)) { Text("🏢 Office desk", fontWeight = FontWeight.SemiBold, color = TextDark)
                    Text("Message the office / your team", color = Muted, fontSize = 11.sp) }
            }
            Spacer(Modifier.height(6.dp))
            AsyncContent(block = { vm.repo.chatContacts() }) { d, _ ->
                val contacts = d["contacts"].l()
                if (contacts.isEmpty()) Text("No contacts on your shared cases yet.", color = Muted, fontSize = 12.sp)
                LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(contacts) { cc -> val c = cc.m()
                        Card(colors = CardDefaults.cardColors(containerColor = CardWhite),
                            modifier = Modifier.fillMaxWidth().clickable { active = c["id"].i() to false; activeName = c["name"].s() }) {
                            Column(Modifier.padding(10.dp)) { Text(c["name"].s(), fontWeight = FontWeight.SemiBold, color = TextDark)
                                Text(c["role"].s(), color = Muted, fontSize = 11.sp) }
                        }
                    }
                }
            }
        } else {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = { active = null }) { Text("‹ Back") }
                Spacer(Modifier.width(8.dp)); Text(activeName, fontWeight = FontWeight.Bold, color = TextDark)
            }
            ChatThread(vm, active!!.first, active!!.second)
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
        Box(Modifier.weight(1f)) {
            AsyncContent(key = "$withId|$office|$tick", block = { vm.repo.chatThread(withId, office) }) { d, _ ->
                val msgs = d["messages"].l()
                LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (msgs.isEmpty()) item { Text("No messages yet. Say hello 👋", color = Muted, fontSize = 12.sp) }
                    items(msgs) { mm -> val m = mm.m(); val mine = m["mine"] == true
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
                            Card(colors = CardDefaults.cardColors(containerColor = if (mine) BrandBlue else Color(0xFFEFF3FF))) {
                                Column(Modifier.padding(8.dp)) {
                                    if (!mine && office) Text(m["from"].s(), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (mine) Color.White else Muted)
                                    Text(m["body"].s(), color = if (mine) Color.White else TextDark, fontSize = 13.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f),
                placeholder = { Text("Type a message…") }, singleLine = true)
            Spacer(Modifier.width(6.dp))
            Button(onClick = {
                val b = text.trim(); if (b.isEmpty()) return@Button; text = ""
                val body: Map<String, Any?> = if (office) mapOf("office" to true, "body" to b) else mapOf("to_id" to withId, "body" to b)
                scope.launch { try { vm.repo.chatSend(body); tick++ } catch (_: Exception) {} }
            }) { Text("Send") }
        }
    }
}
