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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.OfficerLocation
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
    val scope = rememberCoroutineScope()
    var officers by remember { mutableStateOf<List<OfficerLocation>>(emptyList()) }
    var expanded by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<OfficerLocation?>(null) }
    var route by remember { mutableStateOf<List<org.osmdroid.util.GeoPoint>>(emptyList()) }
    var loadingRoute by remember { mutableStateOf(false) }

    // Live refresh every few seconds so agent pins move on their own.
    LaunchedEffect(Unit) {
        while (true) {
            officers = runCatching { vm.repo.liveOfficers() }.getOrNull() ?: officers
            delay(4000)
        }
    }

    fun openHistory(o: OfficerLocation) {
        selected = o; expanded = true; route = emptyList(); loadingRoute = true
        scope.launch {
            val pts = runCatching { vm.repo.officerRoute(o.officerId, null) }.getOrNull().orEmpty()
            route = pts.map { org.osmdroid.util.GeoPoint(it.latitude, it.longitude) }
            loadingRoute = false
        }
    }

    if (expanded) {
        // ---- Expanded: big map with the selected officer's route ----
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
            ) {
                androidx.compose.material3.TextButton(onClick = { expanded = false; route = emptyList() }) {
                    Text("‹ Back to list")
                }
                Column(Modifier.weight(1f)) {
                    Text(selected?.name ?: "Route", fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            loadingRoute -> "Loading today's route…"
                            route.isEmpty() -> "No route recorded today"
                            else -> "${route.size} points · 🟢 S start · 🔴 E end"
                        },
                        style = MaterialTheme.typography.bodySmall, color = Muted,
                    )
                }
            }
            Box(Modifier.fillMaxSize()) {
                OsmLiveMap(officers = officers, scope = scope, routePoints = route,
                    modifier = Modifier.fillMaxSize())
            }
        }
    } else {
        // ---- Default: officer list first, compact live map underneath ----
        Column(Modifier.fillMaxSize()) {
            SectionTitle("Field agents — live", Modifier.padding(start = 16.dp, top = 12.dp))
            LazyColumn(
                Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (officers.isEmpty()) {
                    item {
                        Text("No field agents have shared a location today. They appear here once their app sends a position.",
                            color = Muted, modifier = Modifier.padding(12.dp))
                    }
                }
                items(officers.size) { i ->
                    val o = officers[i]
                    InfoCard {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("● ${o.name}", fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.primary)
                                Text("Last seen: ${o.lastSeen}", style = MaterialTheme.typography.bodySmall, color = Muted)
                            }
                            androidx.compose.material3.OutlinedButton(onClick = { openHistory(o) }) {
                                Text("🕘 History")
                            }
                        }
                    }
                }
            }
            SectionTitle("Live map", Modifier.padding(start = 16.dp, top = 4.dp))
            Box(Modifier.fillMaxWidth().height(280.dp).padding(horizontal = 12.dp, vertical = 8.dp)) {
                OsmLiveMap(officers = officers, scope = scope, modifier = Modifier.fillMaxSize())
            }
        }
    }
}
