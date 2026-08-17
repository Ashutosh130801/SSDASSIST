package `in`.recoveriq.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.BankRow
import `in`.recoveriq.app.data.LeaderRow
import `in`.recoveriq.app.data.Trends
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.TrendStrip
import `in`.recoveriq.app.ui.fos.OnDutyCard
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim

@Composable
fun DashboardScreen(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit = {},
    onRequestBatteryExemption: () -> Unit = {},
) {
    AsyncContent(block = { vm.repo.dashboard() }) { d, _ ->
        LazyColumn(
            Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(if (user.isFieldAgent || user.isTelecaller) "My stats" else "Dashboard",
                    style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text(user.roleLabel + (user.branch?.let { " · $it" } ?: ""), color = Muted)
            }
            // Field officers: the on-duty switch is the first thing on their home screen.
            if (user.isFieldAgent) {
                item { OnDutyCard(vm, onNeedTrackingPermissions, onRequestBatteryExemption) }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Kpi(Modifier.weight(1f), "Cases", d.kpis.totalCases.toString())
                    Kpi(Modifier.weight(1f), "Recovery", "${"%.0f".format(d.kpis.recoveryRate)}%")
                }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Kpi(Modifier.weight(1f), "Received", money(d.kpis.received), Good)
                    Kpi(Modifier.weight(1f), "Pending", money(d.kpis.pending), BrandBlue)
                }
            }
            item {
                InfoCard {
                    Text("Collection progress", fontWeight = FontWeight.SemiBold)
                    val frac = if (d.kpis.target > 0) (d.kpis.received / d.kpis.target).toFloat().coerceIn(0f, 1f) else 0f
                    Text("${money(d.kpis.received)} of ${money(d.kpis.target)} target",
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                    @Suppress("DEPRECATION")
                    LinearProgressIndicator(progress = frac,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp).height(8.dp).clip(RoundedCornerShape(4.dp)))
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                        Pill("Paid", d.kpis.paid, Good)
                        Pill("Partial", d.kpis.partial, BrandBlue)
                        Pill("Unpaid", d.kpis.unpaid, Muted)
                    }
                }
            }
            // FOS / caller: their FTD / MTD / LMTD / Overall achievement (cash collected).
            if (user.isFieldAgent || user.isTelecaller) {
                item {
                    val trends by produceState<Trends?>(initialValue = null) {
                        value = runCatching { vm.repo.myTrends().trends }.getOrNull()
                    }
                    trends?.let { t ->
                        InfoCard { TrendStrip(t, title = "Cash collected — FTD / MTD / LMTD / Overall") }
                    }
                }
            }
            if (d.byBank.isNotEmpty()) {
                item { SectionTitle("By bank") }
                items(d.byBank.size) { i -> BankRowCard(d.byBank[i]) }
            }
            if (d.leaderboard.isNotEmpty()) {
                item { SectionTitle("Field leaderboard") }
                items(d.leaderboard.size) { i -> LeaderRowCard(i + 1, d.leaderboard[i]) }
            }
        }
    }
}

private fun money(v: Double) = "₹${"%,.0f".format(v)}"

@Composable
private fun Kpi(modifier: Modifier, label: String, value: String, color: androidx.compose.ui.graphics.Color = BrandBlue) {
    InfoCard(modifier) {
        Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = color)
        Text(label, style = MaterialTheme.typography.bodySmall, color = Muted)
    }
}

@Composable
private fun Pill(label: String, count: Int, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(count.toString(), fontWeight = FontWeight.Bold, color = color)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MutedDim)
    }
}

@Composable
private fun BankRowCard(b: BankRow) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(b.bank, fontWeight = FontWeight.SemiBold)
                Text("${b.cases} cases", style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(money(b.received), color = Good, fontWeight = FontWeight.Medium)
                Text("pending ${money(b.pending)}", style = MaterialTheme.typography.labelSmall, color = MutedDim)
            }
        }
    }
}

@Composable
private fun LeaderRowCard(rank: Int, l: LeaderRow) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.height(28.dp)) {
                Text("#$rank", fontWeight = FontWeight.Bold, color = BrandBlue)
            }
            Column(Modifier.weight(1f).padding(start = 12.dp)) {
                Text(l.name, fontWeight = FontWeight.SemiBold)
                Text("${l.visits} visits", style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            Text(money(l.collected), color = Good, fontWeight = FontWeight.Medium)
        }
    }
}
