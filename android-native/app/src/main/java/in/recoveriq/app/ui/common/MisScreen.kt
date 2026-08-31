package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Divider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
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

/**
 * Full MIS for a portfolio — the entire web MIS payload rendered on mobile: portfolio picker,
 * month filter, overall + settlement + projection + funnel blocks, and every pivot / leaderboard /
 * insight table. View-only (Excel download stays on web). Gated to MIS roles by the nav.
 */
@Composable
fun MisScreen(vm: AuthViewModel, user: User) {
    var mb by remember { mutableStateOf("current") }
    var bank by remember { mutableStateOf("") }
    var product by remember { mutableStateOf("") }
    val live = rememberLiveKey()

    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SectionTitle("MIS", Modifier.padding(top = 12.dp, start = 4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("current" to "This month", "next" to "Next month", "" to "All months").forEach { (v, l) ->
                FilterChip(selected = mb == v, onClick = { mb = v }, label = { Text(l) })
            }
        }

        AsyncContent(key = "mis-portfolios", block = { vm.repo.productSummary() }) { ports, _ ->
            val banks = ports.map { it.bank }.distinct().sorted()
            LaunchedEffect(banks) { if (bank.isBlank() && banks.isNotEmpty()) bank = banks.first() }
            Text("Portfolio", color = Muted, style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(start = 4.dp))
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                banks.forEach { b ->
                    FilterChip(selected = bank == b, onClick = { bank = b; product = "" }, label = { Text(b) })
                }
            }
            val prods = ports.filter { it.bank == bank }.map { it.product }.distinct().sorted()
            LaunchedEffect(bank, prods) { if (prods.isNotEmpty() && product !in prods) product = prods.first() }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                prods.forEach { p ->
                    FilterChip(selected = product == p, onClick = { product = p }, label = { Text(p) })
                }
            }
        }

        if (bank.isNotBlank() && product.isNotBlank()) {
            AsyncContent(
                key = "mis|$bank|$product|$mb|$live",
                block = { vm.repo.mis(bank = bank, product = product, monthBucket = mb) },
            ) { d, _ -> MisBody(d) }
        }
    }
}

@Composable
private fun MisBody(d: Map<String, Any?>) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        // Header
        val seg = d["segment"]?.toString()
        val base = d["base_label"]?.toString() ?: "ENR"
        InfoCard {
            Text("${d["bank"] ?: "—"} · ${d["product"] ?: "—"}", fontWeight = FontWeight.Bold, color = BrandBlue)
            Text(listOfNotNull(seg?.let { "Segment $it" }, "Recovery base: $base").joinToString(" · "),
                style = MaterialTheme.typography.labelSmall, color = Muted)
        }

        // FTD / MTD / LMTD / Overall
        val tr = d["trends"].asRow()
        if (tr.isNotEmpty()) {
            InfoCard {
                TrendStrip(
                    Trends(ftd = tr.num("ftd"), mtd = tr.num("mtd"), lmtd = tr.num("lmtd"), overall = tr.num("overall")),
                    title = "Cash collected — FTD / MTD / LMTD / Overall",
                )
            }
        }

        // Key/value blocks (overall, settlement, projection, funnel)
        KV_BLOCKS.forEach { (key, title) ->
            val block = d[key].asRow()
            if (block.isNotEmpty()) {
                SectionTitle(title)
                InfoCard { KvBlock(block) }
            }
        }

        // Every pivot / leaderboard / insight table
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
            // header
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
