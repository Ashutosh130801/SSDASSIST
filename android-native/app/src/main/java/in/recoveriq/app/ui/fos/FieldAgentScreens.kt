package `in`.recoveriq.app.ui.fos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.size
import androidx.compose.material3.FilterChip
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.activity.compose.BackHandler
import androidx.compose.material3.OutlinedButton
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.RemindersResponse
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.location.Tracking
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.CaseCard
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.LogoLoader
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.rememberLiveKey
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Warn

@Composable
fun FieldAgentTrackingScreen(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Hello, ${user.name.substringBefore(' ')}", style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold)
        Text(user.roleLabel + (user.branch?.let { " · $it" } ?: ""), color = Muted)

        OnDutyCard(vm, onNeedTrackingPermissions, onRequestBatteryExemption)

        SectionTitle("Today's activity")
        AsyncContent(block = { vm.repo.myTodayRoute() }) { route, _ ->
            InfoCard {
                Text("${route.count} location updates recorded today",
                    style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                if (route.distanceKm > 0) {
                    Spacer(Modifier.height(4.dp))
                    Text("Distance covered: ${route.distanceKm} km",
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                }
                route.points.lastOrNull()?.let { last ->
                    Text("Last fix: ${"%.5f".format(last.lat)}, ${"%.5f".format(last.lng)}",
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                }
            }
        }
    }
}

/** The on-duty on/off switch (+ battery-optimisation nudge). Reusable so it can sit on the
 *  field officer's home dashboard as well as the dedicated On Duty screen. */
@Composable
fun OnDutyCard(
    vm: AuthViewModel,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val onDuty by vm.repo.onDutyFlow.collectAsState(initial = false)
    // If duty was left on (survived a restart), make sure the service is actually running.
    LaunchedEffect(onDuty) { if (onDuty) Tracking.start(context) }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        InfoCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text(if (onDuty) "You're on duty" else "Off duty",
                        style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                        color = if (onDuty) Good else MaterialTheme.colorScheme.onSurface)
                    Text(
                        if (onDuty) "Live location is shared with your branch, even in the background."
                        else "Turn on to start sharing your live location.",
                        style = MaterialTheme.typography.bodySmall, color = Muted,
                    )
                }
                Switch(checked = onDuty, onCheckedChange = { want ->
                    scope.launch { vm.repo.setOnDuty(want) }
                    if (want) {
                        onNeedTrackingPermissions()
                        Tracking.start(context)
                    } else {
                        Tracking.stop(context)
                    }
                })
            }
        }

        if (onDuty) {
            InfoCard {
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Filled.Bolt, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Column {
                        Text("Keep tracking reliable", fontWeight = FontWeight.SemiBold)
                        Text("Allow the app to ignore battery optimisation so Android doesn't pause it.",
                            style = MaterialTheme.typography.bodySmall, color = Muted)
                    }
                }
                TextButton(onClick = onRequestBatteryExemption) { Text("Allow unrestricted battery") }
            }
        }
    }
}

private fun stateRank(s: String) = when (s) { "fresh" -> 0; "touched" -> 1; else -> 2 }

@Composable
private fun RemindersBanner(data: RemindersResponse?, onOpenCase: (Int) -> Unit) {
    val d = data ?: return
    if (d.count == 0) return
    InfoCard(Modifier.padding(horizontal = 16.dp)) {
        Column(Modifier.padding(12.dp)) {
            Text("🔔 PTP reminders · ${d.count}", fontWeight = FontWeight.SemiBold)
            Text("${d.overdue} overdue · ${d.dueToday} due today",
                style = MaterialTheme.typography.labelSmall, color = Muted)
            Spacer(Modifier.height(4.dp))
            d.rows.take(6).forEach { r ->
                Row(
                    Modifier.fillMaxWidth().clickable { onOpenCase(r.caseId) }.padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(r.customer ?: r.account ?: "Case", style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.weight(1f).padding(end = 8.dp))
                    Text("${if (r.overdue) "⚠ " else ""}${r.ptpDate ?: ""}",
                        style = MaterialTheme.typography.labelSmall, color = if (r.overdue) Bad else Warn)
                }
            }
        }
    }
}

private val CASE_FILTERS: List<Pair<String, (Case) -> Boolean>> = listOf(
    "All" to { _ -> true },
    "To do" to { c -> c.workState == "fresh" },
    "Not visited" to { c -> !(c.visited == true || c.visitedToday == true) },
    "Visited" to { c -> c.visited == true || c.visitedToday == true },
    "Unpaid" to { c -> (c.paidStatus ?: "").uppercase() == "UNPAID" },
    "Paid" to { c -> (c.paidStatus ?: "").uppercase() == "PAID" },
    "PTP" to { c -> (c.disposition ?: "").uppercase() in listOf("PTP", "RTP") },
    "🚩 Escalated" to { c -> c.escalated == true },
    "🔖 Flagged" to { c -> !c.reviewColor.isNullOrBlank() },
)

// Sort criteria for the field agent's case list — pending amount only, ascending (default) or descending.
private val CASE_SORTS: List<Pair<String, Comparator<Case>>> = listOf(
    "Pending ↑" to compareBy { it.pendingAmount },
    "Pending ↓" to compareByDescending { it.pendingAmount },
    "Pending NORM ↓" to compareByDescending { it.remainingToNorm ?: 0.0 },
    "Pending STAB ↓" to compareByDescending { it.remainingToStab ?: 0.0 },
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MyCasesScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    val liveKey = rememberLiveKey()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var sel by remember { mutableStateOf("All") }
    var query by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf("Pending ↑") }
    // Drill-down: month  ->  portfolio (bank·product)  ->  cases.
    var month by rememberSaveable { mutableStateOf<String?>(null) }
    var portfolio by rememberSaveable { mutableStateOf<String?>(null) }   // "bank||product"
    var busy by remember { mutableStateOf(false) }
    // Keep data and scroll state above the lazy items. Live updates must not remove the list
    // or restart requests whenever the reminders scroll off screen and back into view.
    val listState = rememberLazyListState()
    var caseData by remember { mutableStateOf<List<Case>?>(null) }
    var reminders by remember { mutableStateOf<RemindersResponse?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var retry by remember { mutableStateOf(0) }
    LaunchedEffect(liveKey, retry) {
        loadError = null
        try {
            caseData = vm.repo.myCases()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            loadError = if (caseData == null) "Couldn't load your accounts. Please retry."
                else "Couldn't refresh. Showing previously loaded accounts."
        }
    }
    LaunchedEffect(liveKey, retry) {
        try {
            reminders = vm.repo.reminders()
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // Retain existing reminders during a temporary connection failure.
        }
    }
    fun changePortfolio(value: String?) {
        portfolio = value
        scope.launch { listState.scrollToItem(0) }
    }
    BackHandler(enabled = portfolio != null) { changePortfolio(null) }

    fun monthOf(c: Case): String = (c.month ?: "").trim().ifEmpty { "—" }
    fun portKey(c: Case): String = "${(c.bank ?: "—")}||${(c.product ?: "—")}"

    // A single vertical scroll surface for headers, reminders, filters and accounts.
    // Fixed headers previously consumed almost all available height on small/large-font phones.
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        state = listState,
        contentPadding = PaddingValues(top = 12.dp, bottom = 160.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item(key = "title") { SectionTitle("My accounts", Modifier.padding(start = 16.dp)) }
        item(key = "reminders") { RemindersBanner(reminders, onOpenCase) }
        item(key = "load-status") {
            loadError?.let { message ->
                Column(Modifier.padding(horizontal = 16.dp)) {
                    Text(message, color = Bad)
                    TextButton(onClick = { retry += 1 }) { Text("Retry") }
                }
            }
            if (caseData == null && loadError == null) {
                Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    LogoLoader()
                }
            }
        }
        val cases = caseData ?: return@LazyColumn
        if (cases.isEmpty()) {
            item(key = "empty") { Text("No cases assigned to you yet.", Modifier.padding(16.dp), color = Muted) }
            return@LazyColumn
        }
        val months = cases.map { monthOf(it) }.distinct().sortedDescending()
        val curMonth = month ?: months.firstOrNull() ?: "—"

        // ---- Month chips (compact, single scrollable line) — months stay separate ----
        item(key = "months") {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Month:", color = Muted, modifier = Modifier.padding(end = 2.dp))
                months.forEach { m ->
                    val n = cases.count { monthOf(it) == m }
                    FilterChip(selected = curMonth == m,
                        onClick = { month = m; changePortfolio(null) },
                        label = { Text("$m ($n)") })
                }
            }
        }
        val monthCases = cases.filter { monthOf(it) == curMonth }

        if (portfolio == null) {
            // ---- Portfolio picker: one card per Bank · Product in this month ----
            val ports = monthCases.groupBy { portKey(it) }.toList().sortedByDescending { it.second.size }
            item(key = "portfolio-heading") { Text("Portfolios in $curMonth", color = Muted,
                modifier = Modifier.padding(start = 16.dp, top = 6.dp, bottom = 2.dp))
            }
            items(ports, key = { "portfolio:$curMonth:${it.first}" }) { (key, list) ->
                val bank = key.substringBefore("||"); val prod = key.substringAfter("||")
                val pend = list.sumOf { it.pendingAmount }
                InfoCard(Modifier.padding(horizontal = 16.dp).fillMaxWidth().clickable { changePortfolio(key) }) {
                    Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("$bank  ·  $prod", fontWeight = FontWeight.Bold, color = BrandBlue)
                            Text("${list.size} account${if (list.size == 1) "" else "s"}  ·  pending ₹${"%,.0f".format(pend)}",
                                style = MaterialTheme.typography.bodySmall, color = Muted)
                        }
                        Text("›", color = Muted, fontWeight = FontWeight.Bold)
                    }
                }
            }
            return@LazyColumn
        }

        // ---- Case list for the selected month + portfolio ----
        val bank = portfolio!!.substringBefore("||"); val prod = portfolio!!.substringAfter("||")
        val portCases = monthCases.filter { portKey(it) == portfolio }
        val pred = CASE_FILTERS.first { it.first == sel }.second
        val q = query.trim().lowercase()
        fun matches(c: Case): Boolean {
            if (q.isEmpty()) return true
            val digits = q.filter { it.isDigit() }
            return listOf(c.customerName, c.accountNo, c.cardNo, c.phone, c.altPhone)
                .any { it != null && it.lowercase().contains(q) } ||
                (digits.isNotEmpty() && listOf(c.accountNo, c.cardNo, c.phone, c.altPhone)
                    .any { it != null && it.filter { ch -> ch.isDigit() }.contains(digits) })
        }
        val comparator = (CASE_SORTS.firstOrNull { it.first == sort } ?: CASE_SORTS.first()).second
        val ordered = portCases.filter { pred(it) && matches(it) }.sortedWith(comparator)
        val exportTitle = "$bank · $prod · $curMonth"
        val exportBase = "Cases_${bank}_${prod}_$curMonth".replace(Regex("[^A-Za-z0-9_-]"), "")

        // Context bar: which portfolio, change link, and Excel / PDF download of the filtered set.
        item(key = "portfolio-context") {
            FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                TextButton(onClick = { changePortfolio(null) }, contentPadding = PaddingValues(horizontal = 4.dp)) {
                    Text("‹ $bank·$prod", color = BrandBlue, fontWeight = FontWeight.SemiBold)
                }
                Text("${ordered.size}", color = Muted)
                Spacer(Modifier.size(6.dp))
                OutlinedButton(onClick = {
                    if (!busy && ordered.isNotEmpty()) { busy = true
                        scope.launch { exportAndShare(ctx, vm, ordered.map { it.id }, "xlsx", exportBase, exportTitle); busy = false }
                    }
                }, contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp)) { Text("⬇ Excel") }
                Spacer(Modifier.size(6.dp))
                OutlinedButton(onClick = {
                    if (!busy && ordered.isNotEmpty()) { busy = true
                        scope.launch { exportAndShare(ctx, vm, ordered.map { it.id }, "pdf", exportBase, exportTitle); busy = false }
                    }
                }, contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp)) { Text("⬇ PDF") }
            }
        }
        // Search
        item(key = "search") {
            OutlinedTextField(
                value = query, onValueChange = { query = it }, singleLine = true,
                leadingIcon = { Icon(Icons.Filled.Search, null) },
                placeholder = { Text("Search name / account / phone") },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = TextDark, unfocusedTextColor = TextDark,
                    cursorColor = BrandBlue, focusedBorderColor = BrandBlue, unfocusedBorderColor = Muted,
                ),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp),
            )
        }
        // Status + sort — one compact scrollable line each.
        item(key = "filters") {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
            ) {
                CASE_FILTERS.forEach { (label, p) ->
                    val n = portCases.count(p)
                    FilterChip(selected = sel == label, onClick = { sel = label }, label = { Text("$label ($n)") })
                }
            }
        }
        item(key = "sort") {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Sort:", color = Muted, modifier = Modifier.padding(end = 2.dp))
                CASE_SORTS.forEach { (label, _) ->
                    FilterChip(selected = sort == label, onClick = { sort = label }, label = { Text(label) })
                }
            }
        }
        if (ordered.isEmpty()) {
            item(key = "empty") {
                Text(if (q.isEmpty()) "No cases in this filter." else "No cases match \"$query\".",
                    Modifier.padding(16.dp), color = Muted)
            }
        } else {
            items(ordered, key = { "case:${it.id}" }) { case ->
                Column(Modifier.padding(horizontal = 16.dp)) {
                    CaseCard(case, onClick = { onOpenCase(case.id) })
                }
            }
        }
    }
}

/** Download the given cases as Excel/PDF from the backend and open the Android share sheet. */
private suspend fun exportAndShare(
    ctx: android.content.Context, vm: AuthViewModel,
    ids: List<Int>, fmt: String, baseName: String, title: String,
) {
    try {
        val ext = if (fmt == "pdf") "pdf" else "xlsx"
        // Do the network read + file write OFF the main thread (a @Streaming body is read from the
        // socket here), then share on the main thread.
        val file = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            val body = vm.repo.exportCases(ids, fmt, title)
            val f = java.io.File(ctx.cacheDir, "$baseName.$ext")
            body.byteStream().use { input -> f.outputStream().use { out -> input.copyTo(out) } }
            f
        }
        val uri = androidx.core.content.FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", file)
        val mime = if (fmt == "pdf") "application/pdf"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
            type = mime
            putExtra(android.content.Intent.EXTRA_STREAM, uri)
            putExtra(android.content.Intent.EXTRA_SUBJECT, "$title — accounts")
            addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        ctx.startActivity(android.content.Intent.createChooser(send, "Share / save")
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: Exception) {
        android.widget.Toast.makeText(ctx, "Download failed: ${e.message}", android.widget.Toast.LENGTH_LONG).show()
    }
}
