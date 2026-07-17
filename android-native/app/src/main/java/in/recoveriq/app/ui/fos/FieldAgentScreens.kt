package `in`.recoveriq.app.ui.fos

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.location.Tracking
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DataList
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted

@Composable
fun FieldAgentTrackingScreen(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val context = LocalContext.current
    var onDuty by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
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
                    onDuty = want
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
        AsyncContent(block = { vm.repo.myTodayRoute() }) { pings, _ ->
            InfoCard {
                Text("${pings.size} location updates recorded today",
                    style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                val last = pings.maxByOrNull { it.createdAt }
                if (last != null) {
                    Spacer(Modifier.height(4.dp))
                    Text("Last fix: ${"%.5f".format(last.latitude)}, ${"%.5f".format(last.longitude)}",
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                }
            }
        }
    }
}

@Composable
fun MyCasesScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize()) {
        SectionTitle("My assigned cases", Modifier.padding(start = 16.dp, top = 12.dp))
        AsyncContent(block = { vm.repo.myCases() }) { cases, _ ->
            DataList(cases, emptyText = "No cases assigned to you yet.") { c -> CaseRow(c) }
        }
    }
}

@Composable
fun CaseRow(c: Case) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(c.customerName ?: "Unnamed customer", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(c.bank, c.bucket, c.pincode).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
                c.address?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Muted) }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("₹${"%,.0f".format(c.pendingAmount)}", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                c.status?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = Muted) }
            }
        }
    }
}
