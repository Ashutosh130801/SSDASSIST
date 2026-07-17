package `in`.recoveriq.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.CaseCard
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Muted

@Composable
fun AdminDashboardScreen(vm: AuthViewModel, user: User, onOpenCase: (Int) -> Unit) {
    AsyncContent(block = { vm.repo.allCases() }) { cases, _ ->
        val total = cases.size
        val recovered = cases.sumOf { it.receivedAmount }
        val outstanding = cases.sumOf { it.pendingAmount }
        val resolved = cases.count { (it.status ?: "").equals("resolved", true) || (it.paidStatus ?: "").equals("paid", true) }

        LazyColumn(
            Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text("Dashboard", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text(user.roleLabel, color = Muted)
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Kpi(Modifier.weight(1f), "Total cases", total.toString())
                    Kpi(Modifier.weight(1f), "Resolved", resolved.toString())
                }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Kpi(Modifier.weight(1f), "Recovered", "₹${"%,.0f".format(recovered)}")
                    Kpi(Modifier.weight(1f), "Outstanding", "₹${"%,.0f".format(outstanding)}")
                }
            }
            item { SectionTitle("Highest outstanding") }
            val top = cases.sortedByDescending { it.pendingAmount }.take(15)
            items(top.size) { i -> CaseCard(top[i], onClick = { onOpenCase(top[i].id) }) }
        }
    }
}

@Composable
private fun Kpi(modifier: Modifier, label: String, value: String) {
    InfoCard(modifier) {
        Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary)
        Text(label, style = MaterialTheme.typography.bodySmall, color = Muted)
    }
}

@Composable
private fun CaseLine(c: Case) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(c.customerName ?: "Unnamed", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(c.bank, c.bucket).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            Text("₹${"%,.0f".format(c.pendingAmount)}", fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary)
        }
    }
}

@Composable
fun LiveMapScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize()) {
        SectionTitle("Field agents — live", Modifier.padding(start = 16.dp, top = 12.dp))
        AsyncContent(block = { vm.repo.liveOfficers() }) { officers, reload ->
            Box(Modifier.fillMaxSize()) {
                OsmLiveMap(officers = officers, modifier = Modifier.fillMaxSize())
            }
        }
    }
}
