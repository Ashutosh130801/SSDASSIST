package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.FilterOptions
import `in`.recoveriq.app.data.ProductSummary
import `in`.recoveriq.app.data.Trends
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim

/* ---- helpers to read the generic MIS map (Moshi → Map/List/Double/Boolean/String) ---- */

@Suppress("UNCHECKED_CAST")
private fun Any?.asRow(): Map<String, Any?> = (this as? Map<String, Any?>) ?: emptyMap()

@Suppress("UNCHECKED_CAST")
private fun Any?.asRows(): List<Map<String, Any?>> =
    (this as? List<*>)?.mapNotNull { it as? Map<String, Any?> } ?: emptyList()

private fun Map<String, Any?>.num(k: String): Double = (this[k] as? Number)?.toDouble() ?: 0.0

private val MONEY_HEADERS = setOf(
    "ENR", "PAID ENR", "PENDING", "COLLECTED", "CASH COLL", "TARGET ENR",
    "ACHIEVED ENR", "GAP ENR", "ROLLBACK COLL", "VALUE",
)

/** Format one cell the way the web MIS shows it: % columns as %, money columns with ₹, the rest plain. */
private fun fmtCell(header: String, v: Any?): String {
    if (v == null) return "—"
    if (v is Boolean) return if (v) "Yes" else "—"
    val num = (v as? Number)?.toDouble() ?: v.toString().toDoubleOrNull()
    if (num != null) {
        if (header.contains("%")) return "%.1f%%".format(num)
        if (header.uppercase() in MONEY_HEADERS) return "₹" + "%,.0f".format(num)
        return if (num == Math.floor(num) && !num.isInfinite()) "%,.0f".format(num) else "%,.2f".format(num)
    }
    return v.toString()
}

private fun prettyKey(k: String): String =
    k.replace("_", " ").replaceFirstChar { it.uppercase() }

/* ---- table + block definitions mirrored from the backend (TABLE_NAMES / _TABLE_COLS) ---- */

private val GROUP_COLS = listOf(
    "label" to "NAME", "count" to "COUNT", "paid" to "PAID", "unpaid" to "UNPAID",
    "enr" to "ENR", "paid_enr" to "PAID ENR", "pct" to "PAID %", "norm_pct" to "NORM %",
    "stab_pct" to "STAB %", "rollback_pct" to "ROLLBACK %", "rollback_collected" to "ROLLBACK COLL",
    "amount" to "CASH COLL", "visited" to "VISITED", "not_visited" to "NOT VISITED",
)
private val AREA_COLS = listOf(
    "label" to "AREA", "count" to "COUNT", "paid" to "PAID", "unpaid" to "UNPAID",
    "enr" to "ENR", "pending" to "PENDING", "amount" to "COLLECTED", "recovery_pct" to "RECOVERY %",
    "pct" to "PAID %", "norm_pct" to "NORM %", "stab_pct" to "STAB %",
)
private val CASELIST_COLS = listOf(
    "customer" to "Customer", "account" to "Account", "pending" to "Pending", "enr" to "ENR",
    "propensity" to "Score", "fos" to "FOS", "caller" to "Caller", "contacted" to "Contacted",
)
private val NS_CASELIST_COLS = listOf(
    "customer" to "Customer", "account" to "Account", "norm" to "NORM", "pending_norm" to "Pending NORM",
    "stab" to "STAB", "pending_stab" to "Pending STAB", "pending" to "Pending",
    "fos" to "FOS", "caller" to "Caller", "contacted" to "Contacted",
)
private val LEADERBOARD_COLS = listOf(
    "emp" to "EMP NAME", "count" to "COUNT", "unpaid" to "UNPAID", "paid" to "PAID", "enr" to "ENR",
    "target_pct" to "TARGET %", "target_enr" to "TARGET ENR", "achieved_pct" to "ACHIEVED %",
    "achieved_enr" to "ACHIEVED ENR", "gap_enr" to "GAP ENR", "to_target_pct" to "TO TARGET %",
    "status" to "STATUS", "pending_visit" to "PENDING VISIT", "cash_coll" to "CASH COLL",
)

// (key, title, columns) in the same order the web MIS lists them.
private val TABLES: List<Triple<String, String, List<Pair<String, String>>>> = listOf(
    Triple("leaderboard", "Employee performance & leaderboard", LEADERBOARD_COLS),
    Triple("by_fos", "FOS-wise", GROUP_COLS),
    Triple("by_caller", "Caller-wise", GROUP_COLS),
    Triple("by_area", "Area-wise recovery", AREA_COLS),
    Triple("by_team_lead", "Team-lead wise", GROUP_COLS),
    Triple("by_cat", "Category-wise", GROUP_COLS),
    Triple("by_dpd", "Bucket (DPD) recovery", GROUP_COLS),
    Triple("aging", "Contact aging", listOf("label" to "Recency", "count" to "Count", "pending" to "Pending")),
    Triple("untouched_table", "Untouched high-value cases", CASELIST_COLS),
    Triple("top_by_norm", "High-value by NORM", NS_CASELIST_COLS),
    Triple("top_by_stab", "High-value by STAB", NS_CASELIST_COLS),
    Triple("top_pending", "Top pending cases", CASELIST_COLS),
    Triple("priority", "Propensity worklist", CASELIST_COLS),
    Triple("obstacles", "Obstacle rates",
        listOf("caller" to "Caller", "total" to "Total", "obstacles" to "Obstacles", "rate_pct" to "Rate %")),
    Triple("productivity", "Productivity (today)",
        listOf("emp" to "Employee", "calls_today" to "Calls today", "visits_today" to "Visits today", "idle" to "Idle")),
    Triple("field_efficiency", "FOS field efficiency",
        listOf("fos" to "FOS", "visits" to "Visits", "distance_km" to "Distance km",
            "off_location" to "Off-location", "collected" to "Collected")),
    Triple("trend", "Collection trend (30d)", listOf("date" to "Date", "collected" to "Collected")),
)

// dict blocks shown as key/value cards, in web order.
private val KV_BLOCKS = listOf(
    "overall" to "Overall summary",
    "settlement" to "Settlement leakage & realization",
    "projection" to "Month-end projection",
    "funnel" to "Conversion & PTP funnel",
)

/** Everything currently selected in the filter sheet. */
private data class MisFilters(
    val branches: Set<String> = emptySet(),
    val area: String = "",
    val cycles: Set<String> = emptySet(),
    val fos: Set<Int> = emptySet(),
    val callers: Set<Int> = emptySet(),
) {
    val count: Int get() = branches.size + (if (area.isNotBlank()) 1 else 0) + cycles.size + fos.size + callers.size
    fun csv(s: Set<Int>) = s.joinToString(",")
    fun csvStr(s: Set<String>) = s.joinToString(",")
}

/**
 * Full MIS for a portfolio — the entire web MIS payload rendered on mobile: portfolio picker,
 * month filter, an e-commerce-style Filters sheet (branch / area / cycle / FOS / caller), and
 * every pivot / leaderboard / insight table. View-only. Gated to MIS roles by the nav.
 */
@Composable
fun MisScreen(vm: AuthViewModel, user: User) {
    var mb by remember { mutableStateOf("current") }
    var bank by remember { mutableStateOf("") }
    var product by remember { mutableStateOf("") }
    var ports by remember { mutableStateOf<List<ProductSummary>>(emptyList()) }
    var fopts by remember { mutableStateOf(FilterOptions()) }
    var areas by remember { mutableStateOf<List<String>>(emptyList()) }
    var filters by remember { mutableStateOf(MisFilters()) }
    var sheetOpen by remember { mutableStateOf(false) }
    val live = rememberLiveKey()

    // Portfolios once.
    LaunchedEffect(Unit) {
        ports = runCatching { vm.repo.productSummary() }.getOrDefault(emptyList())
    }
    val banks = remember(ports) { ports.map { it.bank }.distinct().sorted() }
    LaunchedEffect(banks) { if (bank.isBlank() && banks.isNotEmpty()) bank = banks.first() }
    val prods = remember(ports, bank) { ports.filter { it.bank == bank }.map { it.product }.distinct().sorted() }
    LaunchedEffect(bank, prods) { if (prods.isNotEmpty() && product !in prods) product = prods.first() }

    // Branch options come from the selected portfolio row; area + cycle/FOS/caller from the API.
    val branchOpts = remember(ports, bank, product) {
        ports.filter { it.bank == bank && it.product == product }
            .flatMap { it.branches }.map { it.branch }.filter { it.isNotBlank() }.distinct().sorted()
    }
    LaunchedEffect(bank, product) {
        filters = MisFilters()                       // reset filters when the portfolio changes
        if (bank.isNotBlank() && product.isNotBlank()) {
            fopts = runCatching { vm.repo.filterOptions(bank, product) }.getOrDefault(FilterOptions())
            areas = runCatching { vm.repo.areas(bank, product) }.getOrDefault(emptyList())
        }
    }

    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SectionTitle("MIS", Modifier.padding(top = 12.dp, start = 4.dp))

        // Month + Filters bar — compact, one row, opens the sheet (Flipkart style).
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("current" to "This month", "next" to "Next month", "" to "All months").forEach { (v, l) ->
                    FilterChip(selected = mb == v, onClick = { mb = v }, label = { Text(l) })
                }
            }
            FilterButton(filters.count) { sheetOpen = true }
        }

        // Portfolio picker (bank → product).
        Text("Portfolio", color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 4.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            banks.forEach { b -> FilterChip(selected = bank == b, onClick = { bank = b; product = "" }, label = { Text(b) }) }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            prods.forEach { p -> FilterChip(selected = product == p, onClick = { product = p }, label = { Text(p) }) }
        }

        // Active-filter chips (removable) — only appears when something is on, so it costs no space otherwise.
        if (filters.count > 0) ActiveFilterChips(filters, fopts) { filters = it }

        if (bank.isNotBlank() && product.isNotBlank()) {
            val fkey = "${filters.branches}|${filters.area}|${filters.cycles}|${filters.fos}|${filters.callers}"
            AsyncContent(
                key = "mis|$bank|$product|$mb|$fkey|$live",
                block = {
                    vm.repo.mis(
                        bank = bank, product = product, monthBucket = mb, area = filters.area,
                        branch = filters.csvStr(filters.branches), cycles = filters.csvStr(filters.cycles),
                        fosIds = filters.csv(filters.fos), callerIds = filters.csv(filters.callers),
                    )
                },
            ) { d, _ -> MisBody(d) }
        }
    }

    if (sheetOpen) {
        FilterSheet(
            branchOpts = branchOpts, areas = areas, fopts = fopts, initial = filters,
            onApply = { filters = it; sheetOpen = false },
            onDismiss = { sheetOpen = false },
        )
    }
}

@Composable
private fun FilterButton(count: Int, onClick: () -> Unit) {
    Surface(
        color = if (count > 0) BrandBlue.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.clickable { onClick() },
    ) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(Icons.Filled.Tune, "Filters", tint = BrandBlue, modifier = Modifier.width(18.dp))
            Text("Filters", color = BrandBlue, fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.labelLarge)
            if (count > 0) Badge(containerColor = BrandBlue) { Text("$count") }
        }
    }
}

@Composable
private fun ActiveFilterChips(filters: MisFilters, fopts: FilterOptions, onChange: (MisFilters) -> Unit) {
    val fosName = { id: Int -> fopts.fos.firstOrNull { it.id == id }?.name ?: "FOS #$id" }
    val callerName = { id: Int -> fopts.callers.firstOrNull { it.id == id }?.name ?: "Caller #$id" }
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (filters.area.isNotBlank())
            RemChip("Area: ${filters.area}") { onChange(filters.copy(area = "")) }
        filters.branches.forEach { b -> RemChip("Branch: $b") { onChange(filters.copy(branches = filters.branches - b)) } }
        filters.cycles.forEach { c -> RemChip("Cyc $c") { onChange(filters.copy(cycles = filters.cycles - c)) } }
        filters.fos.forEach { id -> RemChip(fosName(id)) { onChange(filters.copy(fos = filters.fos - id)) } }
        filters.callers.forEach { id -> RemChip(callerName(id)) { onChange(filters.copy(callers = filters.callers - id)) } }
    }
}

@Composable
private fun RemChip(text: String, onRemove: () -> Unit) {
    Surface(color = BrandBlue.copy(alpha = 0.10f), shape = RoundedCornerShape(8.dp)) {
        Row(Modifier.clickable { onRemove() }.padding(start = 10.dp, end = 6.dp, top = 5.dp, bottom = 5.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(text, color = BrandBlue, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Medium)
            Icon(Icons.Filled.Close, "Remove", tint = BrandBlue, modifier = Modifier.width(14.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterSheet(
    branchOpts: List<String>, areas: List<String>, fopts: FilterOptions,
    initial: MisFilters, onApply: (MisFilters) -> Unit, onDismiss: () -> Unit,
) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var draft by remember { mutableStateOf(initial) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Filters", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                TextButton(onClick = { draft = MisFilters() }) { Text("Clear all") }
            }
            Box(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (branchOpts.isNotEmpty()) FilterGroup("Branch", branchOpts, draft.branches) {
                        draft = draft.copy(branches = it)
                    }
                    if (areas.isNotEmpty()) SingleGroup("Area", areas, draft.area) { draft = draft.copy(area = it) }
                    if (fopts.cycles.isNotEmpty()) FilterGroup("Cycle", fopts.cycles, draft.cycles) {
                        draft = draft.copy(cycles = it)
                    }
                    if (fopts.fos.isNotEmpty()) FilterGroupInt("FOS", fopts.fos.map { it.id to (it.name ?: "#${it.id}") }, draft.fos) {
                        draft = draft.copy(fos = it)
                    }
                    if (fopts.callers.isNotEmpty()) FilterGroupInt("Caller", fopts.callers.map { it.id to (it.name ?: "#${it.id}") }, draft.callers) {
                        draft = draft.copy(callers = it)
                    }
                    if (branchOpts.isEmpty() && areas.isEmpty() && fopts.cycles.isEmpty() &&
                        fopts.fos.isEmpty() && fopts.callers.isEmpty()) {
                        Text("No filters available for this portfolio.", color = Muted,
                            style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f)) { Text("Cancel") }
                Button(onClick = { onApply(draft) }, modifier = Modifier.weight(1f)) {
                    Text(if (draft.count > 0) "Apply (${draft.count})" else "Apply")
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterGroup(title: String, options: List<String>, selected: Set<String>, onChange: (Set<String>) -> Unit) {
    Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(top = 8.dp))
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { opt ->
            FilterChip(selected = opt in selected, onClick = {
                onChange(if (opt in selected) selected - opt else selected + opt)
            }, label = { Text(opt) })
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SingleGroup(title: String, options: List<String>, selected: String, onChange: (String) -> Unit) {
    Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(top = 8.dp))
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { opt ->
            FilterChip(selected = opt == selected, onClick = { onChange(if (opt == selected) "" else opt) },
                label = { Text(opt) })
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterGroupInt(title: String, options: List<Pair<Int, String>>, selected: Set<Int>, onChange: (Set<Int>) -> Unit) {
    Text(title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(top = 8.dp))
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (id, name) ->
            FilterChip(selected = id in selected, onClick = {
                onChange(if (id in selected) selected - id else selected + id)
            }, label = { Text(name) })
        }
    }
}

@Composable
private fun MisBody(d: Map<String, Any?>) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        val seg = d["segment"]?.toString()
        val base = d["base_label"]?.toString() ?: "ENR"
        InfoCard {
            Text("${d["bank"] ?: "—"} · ${d["product"] ?: "—"}", fontWeight = FontWeight.Bold, color = BrandBlue)
            Text(listOfNotNull(seg?.let { "Segment $it" }, "Recovery base: $base").joinToString(" · "),
                style = MaterialTheme.typography.labelSmall, color = Muted)
        }

        val tr = d["trends"].asRow()
        if (tr.isNotEmpty()) {
            InfoCard {
                TrendStrip(
                    Trends(ftd = tr.num("ftd"), mtd = tr.num("mtd"), lmtd = tr.num("lmtd"), overall = tr.num("overall")),
                    title = "Cash collected — FTD / MTD / LMTD / Overall",
                )
            }
        }

        KV_BLOCKS.forEach { (key, title) ->
            val block = d[key].asRow()
            if (block.isNotEmpty()) {
                SectionTitle(title)
                InfoCard { KvBlock(block) }
            }
        }

        TABLES.forEach { (key, title, cols) ->
            val rows = d[key].asRows()
            if (rows.isNotEmpty()) {
                SectionTitle(title)
                MisTable(cols, rows)
            }
        }
    }
}

@Composable
private fun KvBlock(block: Map<String, Any?>) {
    Column(Modifier.fillMaxWidth()) {
        block.entries.forEachIndexed { i, (k, v) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(prettyKey(k), color = Muted, style = MaterialTheme.typography.bodySmall)
                Text(fmtCell(if (k.contains("pct")) "%" else prettyKey(k), v),
                    fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodySmall)
            }
            if (i < block.size - 1) Divider(color = MutedDim.copy(alpha = 0.15f))
        }
    }
}

@Composable
private fun MisTable(cols: List<Pair<String, String>>, rows: List<Map<String, Any?>>) {
    val firstW = 150.dp
    val cellW = 96.dp
    InfoCard {
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            Row {
                cols.forEachIndexed { i, (_, header) ->
                    Text(header, Modifier.width(if (i == 0) firstW else cellW).padding(end = 8.dp, bottom = 4.dp),
                        fontWeight = FontWeight.Bold, color = BrandBlue, style = MaterialTheme.typography.labelSmall)
                }
            }
            Divider(color = MutedDim.copy(alpha = 0.25f))
            rows.forEach { row ->
                Row(Modifier.padding(vertical = 3.dp)) {
                    cols.forEachIndexed { i, (k, header) ->
                        Text(fmtCell(header, row[k]),
                            Modifier.width(if (i == 0) firstW else cellW).padding(end = 8.dp),
                            fontWeight = if (i == 0) FontWeight.Medium else FontWeight.Normal,
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
