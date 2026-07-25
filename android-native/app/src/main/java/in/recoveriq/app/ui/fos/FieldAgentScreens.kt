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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.foundation.clickable
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.RemindersResponse
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.location.Tracking
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.CaseCard
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.rememberLiveKey
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.Warn

@Composable
fun FieldAgentTrackingScreen(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val onDuty by vm.repo.onDutyFlow.collectAsState(initial = false)

    // If duty was left on (survived a restart), make sure the service is actually running.
    LaunchedEffect(onDuty) { if (onDuty) Tracking.start(context) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Hello, ${user.name.substringBefore(' ')}", style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold)
        Text(user.roleLabel + (user.branch?.let { " · $it" } ?: ""), color = Muted)

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

private fun stateRank(s: String) = when (s) { "fresh" -> 0; "touched" -> 1; else -> 2 }

@Composable
private fun RemindersBanner(vm: AuthViewModel, liveKey: Long, onOpenCase: (Int) -> Unit) {
    var data by remember { mutableStateOf<RemindersResponse?>(null) }
    LaunchedEffect(liveKey) { data = runCatching { vm.repo.reminders() }.getOrNull() }
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
                    Text(r.customer ?: r.account ?: "Case", style = MaterialTheme.typography.bodySmall)
                    Text("${if (r.overdue) "⚠ " else ""}${r.ptpDate ?: ""}",
                        style = MaterialTheme.typography.labelSmall, color = if (r.overdue) Bad else Warn)
                }
            }
        }
    }
}

@Composable
fun MyCasesScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    val liveKey = rememberLiveKey()
    Column(Modifier.fillMaxSize()) {
        SectionTitle("My assigned cases", Modifier.padding(start = 16.dp, top = 12.dp))
        RemindersBanner(vm, liveKey, onOpenCase)
        AsyncContent(key = liveKey, block = { vm.repo.myCases() }) { cases, _ ->
            if (cases.isEmpty()) {
                EmptyState("No cases assigned to you yet.")
            } else {
                // Untouched & highest-priority on top; visited/contacted below; paid last.
                val ordered = cases.sortedWith(
                    compareBy({ stateRank(it.workState) }, { -(it.propensity ?: 0) }, { -it.pendingAmount }),
                )
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(ordered.size) { i -> CaseCard(ordered[i], onClick = { onOpenCase(ordered[i].id) }) }
                }
            }
        }
    }
}
