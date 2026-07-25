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
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.rememberLiveKey
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
    val buckets = listOf("overdue", "today", "upcoming")
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("Promise-to-pay tracker", Modifier.padding(top = 12.dp, start = 4.dp))
        AsyncContent(block = { vm.repo.ptpTracker() }) { resp, _ ->
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
    CaseCard(row.case, onClick = { onOpenCase(row.case.id) }, subtitle = promise)
}
