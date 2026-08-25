package `in`.recoveriq.app.ui.caller

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.PtpRow
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.CaseCard
import `in`.recoveriq.app.ui.common.DatePickerField
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.rememberLiveKey
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.Alignment
import androidx.compose.material3.TextButton
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.Warn

@Composable
fun CallQueueScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var seg by remember { mutableStateOf("Due now") }
    val liveKey = rememberLiveKey()
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("Call queue", Modifier.padding(top = 12.dp, start = 4.dp))
        AsyncContent(key = liveKey, block = { vm.repo.callQueue() }) { q, _ ->
            val segments = listOf(
                "Due now" to q.due,
                "Contacted" to q.contactedToday,
                "Upcoming" to q.upcoming,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                segments.forEach { (label, list) ->
                    FilterChip(
                        selected = seg == label,
                        onClick = { seg = label },
                        label = { Text("$label (${list.size})") },
                    )
                }
            }
            val current = segments.first { it.first == seg }.second
            if (current.isEmpty()) {
                EmptyState("Nothing here right now.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize().padding(top = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp),
                ) {
                    items(current.size) { i -> CaseCard(current[i], onClick = { onOpenCase(current[i].id) }) }
                }
            }
        }
    }
}

@Composable
fun PtpTrackerScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var bucket by remember { mutableStateOf("overdue") }
    var dFrom by remember { mutableStateOf("") }
    var dTo by remember { mutableStateOf("") }
    val buckets = listOf("overdue", "today", "upcoming")
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("Promise-to-pay tracker", Modifier.padding(top = 12.dp, start = 4.dp))
        // Promise-date calendar range.
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp)) {
            Box(Modifier.weight(1f)) { DatePickerField("From", dFrom) { dFrom = it } }
            Box(Modifier.weight(1f)) { DatePickerField("To", dTo) { dTo = it } }
            if (dFrom.isNotBlank() || dTo.isNotBlank())
                TextButton(onClick = { dFrom = ""; dTo = "" }) { Text("Clear") }
        }
        AsyncContent(key = "$dFrom|$dTo", block = { vm.repo.ptpTracker(dateFrom = dFrom, dateTo = dTo) }) { resp, _ ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                buckets.forEach { b ->
                    val n = resp.counts[b] ?: 0
                    FilterChip(selected = bucket == b, onClick = { bucket = b },
                        label = { Text("${b.replaceFirstChar { it.uppercase() }} ($n)") })
                }
            }
            val rows = resp.rows.filter { it.bucket == bucket }
            if (rows.isEmpty()) {
                EmptyState("No promises in this group.")
            } else {
                LazyColumn(
                    Modifier.fillMaxSize().padding(top = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp),
                ) {
                    items(rows.size) { i -> PtpCard(rows[i], onOpenCase) }
                }
            }
        }
    }
}

@Composable
private fun PtpCard(row: PtpRow, onOpenCase: (Int) -> Unit) {
    val color = when (row.bucket) {
        "overdue" -> Bad; "today" -> Warn; else -> Good
    }
    val promise = buildString {
        row.ptpAmount?.let { append("₹${"%,.0f".format(it)} promised") }
        row.promisedDate?.let {
            if (isNotEmpty()) append(" · ")
            append("by ${DateUtil.humanDate(it)}")
        }
    }.ifBlank { "Promise to pay" }
    Column {
        CaseCard(row.case, onClick = { onOpenCase(row.case.id) }, subtitle = promise)
        if (row.notes.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().padding(start = 12.dp, top = 2.dp, bottom = 2.dp)) {
                Text("Recent notes", color = Muted, style = MaterialTheme.typography.labelSmall)
                row.notes.take(5).forEach { n ->
                    val head = listOfNotNull(n.disposition?.ifBlank { null }, n.text?.ifBlank { null }).joinToString(": ")
                    val tail = listOfNotNull(n.by?.ifBlank { null }, n.at?.ifBlank { null }).joinToString(", ")
                    Text(
                        (if (n.source == "visit") "🧍 " else "📞 ") + head + (if (tail.isNotBlank()) "  — $tail" else ""),
                        color = Muted, style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(top = 1.dp),
                    )
                }
            }
        }
    }
}
