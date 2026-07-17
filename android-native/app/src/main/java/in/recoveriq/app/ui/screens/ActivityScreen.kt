package `in`.recoveriq.app.ui.screens

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
import `in`.recoveriq.app.data.ActivityItem
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.Warn

@Composable
fun ActivityScreen(vm: AuthViewModel) {
    var kind by remember { mutableStateOf("all") }
    val kinds = listOf("all", "visits", "calls", "payments")

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("Activity", Modifier.padding(top = 12.dp, start = 4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
            kinds.forEach { k ->
                FilterChip(selected = kind == k, onClick = { kind = k },
                    label = { Text(k.replaceFirstChar { it.uppercase() }) })
            }
        }
        AsyncContent(key = kind, block = { vm.repo.activity(kind) }) { items, _ ->
            if (items.isEmpty()) EmptyState("No recent activity.")
            else LazyColumn(
                Modifier.fillMaxSize().padding(top = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp),
            ) {
                items(items.size) { i -> ActivityCard(items[i]) }
            }
        }
    }
}

@Composable
private fun ActivityCard(a: ActivityItem) {
    val color = when (a.type) {
        "payment" -> Good; "visit" -> BrandBlue; "call" -> Warn; else -> Muted
    }
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text("${a.type.replaceFirstChar { it.uppercase() }} · ${a.customer ?: "—"}",
                    fontWeight = FontWeight.SemiBold, color = color)
                if (!a.detail.isNullOrBlank())
                    Text(a.detail, style = MaterialTheme.typography.bodySmall, color = Muted)
                if (!a.note.isNullOrBlank())
                    Text(a.note, style = MaterialTheme.typography.bodySmall, color = Muted)
                Text(listOfNotNull(a.bank, a.by?.let { "by $it" }).joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall, color = Muted)
                if (a.offLocation == true)
                    Text("⚠ Off-location visit", style = MaterialTheme.typography.labelSmall, color = Bad)
            }
            Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                if ((a.amount ?: 0.0) > 0.0)
                    Text("₹${"%,.0f".format(a.amount)}", fontWeight = FontWeight.Bold, color = Good)
                Text(DateUtil.humanTime(a.at), style = MaterialTheme.typography.labelSmall, color = Muted)
            }
        }
    }
}
