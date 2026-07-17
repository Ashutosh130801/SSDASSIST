package `in`.recoveriq.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Device
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.StatusChip
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.launch

@Composable
fun DevicesScreen(vm: AuthViewModel) {
    var refresh by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("Registered devices", Modifier.padding(top = 12.dp, start = 4.dp))
        AsyncContent(key = refresh, block = { vm.repo.devices() }) { devices, _ ->
            if (devices.isEmpty()) EmptyState("No devices registered.")
            else LazyColumn(
                Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp),
            ) {
                items(devices.size) { i ->
                    DeviceCard(
                        devices[i],
                        onApprove = { scope.launch { runCatching { vm.repo.approveDevice(devices[i].id) }; refresh++ } },
                        onRevoke = { scope.launch { runCatching { vm.repo.revokeDevice(devices[i].id) }; refresh++ } },
                    )
                }
            }
        }
    }
}

@Composable
private fun DeviceCard(d: Device, onApprove: () -> Unit, onRevoke: () -> Unit) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(d.userName ?: "User #${d.userId}", fontWeight = FontWeight.SemiBold)
                Text(d.label ?: d.deviceId, style = MaterialTheme.typography.bodySmall, color = Muted)
                d.userBranch?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = Muted) }
            }
            StatusChip(if (d.approved) "approved" else "pending")
        }
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!d.approved) Button(onClick = onApprove, modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = Good)) { Text("Approve") }
            else OutlinedButton(onClick = onRevoke, modifier = Modifier.weight(1f)) { Text("Revoke") }
        }
    }
}
