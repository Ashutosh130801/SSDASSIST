package `in`.recoveriq.app.ui.teamlead

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.TeamMemberCard
import `in`.recoveriq.app.data.Trends
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.Actions
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.TrendStrip
import `in`.recoveriq.app.ui.common.rememberLiveKey
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.Warn

private fun money(v: Double) = "₹" + "%,.0f".format(v)

@Composable
fun TeamLeadDashboardScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    val liveKey = rememberLiveKey()
    AsyncContent(key = liveKey, block = { vm.repo.teamOverview() }) { ov, _ ->
        val k = ov.kpis
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text("My team" + (ov.lead?.branch?.let { " · $it" } ?: ""),
                    style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Kpi(Modifier.weight(1f), "Members", "${k.members}", "${k.fos} FOS · ${k.callers} callers")
                    Kpi(Modifier.weight(1f), "Cases", "${k.cases}", "${k.resolved} resolved")
                }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Kpi(Modifier.weight(1f), "Recovered", money(k.recovered), null, Good)
                    Kpi(Modifier.weight(1f), "Pending", money(k.pending), null, Warn)
                    Kpi(Modifier.weight(1f), "Recovery", "%.1f%%".format(k.recoveryPct), null)
                }
            }
            item { SectionTitle("Members") }
            if (ov.members.isEmpty()) {
                item { EmptyState("No team members yet.") }
            } else {
                items(ov.members.size) { i -> MemberCard(vm, ov.members[i]) }
            }
        }
    }
}

@Composable
private fun Kpi(modifier: Modifier, label: String, value: String, sub: String?, color: androidx.compose.ui.graphics.Color = BrandBlue) {
    InfoCard(modifier) {
        Text(value, fontWeight = FontWeight.Bold, color = color, style = MaterialTheme.typography.titleLarge)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Muted)
        if (sub != null) Text(sub, style = MaterialTheme.typography.labelSmall, color = Muted)
    }
}

@Composable
private fun MemberCard(vm: AuthViewModel, m: TeamMemberCard) {
    val context = LocalContext.current
    InfoCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(m.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
                Text(roleLabel(m.role) + (m.empCode?.let { " · $it" } ?: "") + (m.phone?.let { " · $it" } ?: ""),
                    style = MaterialTheme.typography.labelSmall, color = Muted)
            }
            Text("%.0f%%".format(m.recoveryPct), fontWeight = FontWeight.Bold, color = BrandBlue)
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Cases ${m.assigned}", style = MaterialTheme.typography.labelSmall, color = Muted)
            Text("Resolved ${m.resolved}", style = MaterialTheme.typography.labelSmall, color = Good)
            Text("Recovered ${money(m.recovered)}", style = MaterialTheme.typography.labelSmall, color = Good)
        }
        m.today?.let { t ->
            val line = if (t.label == "visits") "${t.count} visits today"
            else "${t.count} calls today · ${t.ptp ?: 0} PTP"
            Text(line, style = MaterialTheme.typography.labelSmall, color = Muted)
        }
        // FTD / MTD / LMTD / Overall achievement for this team member.
        val trends by produceState<Trends?>(initialValue = null, m.id) {
            value = runCatching { vm.repo.employeeTrends(m.id).trends }.getOrNull()
        }
        trends?.let { t ->
            Spacer(Modifier.height(8.dp))
            TrendStrip(t, title = "Cash collected — FTD / MTD / LMTD / Overall")
        }
        if (!m.phone.isNullOrBlank()) {
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = { Actions.dial(context, m.phone) }) {
                Icon(Icons.Filled.Call, null, Modifier.size(18.dp)); Spacer(Modifier.size(6.dp)); Text("Call ${m.name.substringBefore(' ')}")
            }
        }
    }
}

private fun roleLabel(r: String) = when (r) {
    "fos" -> "Field Agent"; "telecaller" -> "Tele-calling Agent"; else -> r.replaceFirstChar { it.uppercase() }
}
