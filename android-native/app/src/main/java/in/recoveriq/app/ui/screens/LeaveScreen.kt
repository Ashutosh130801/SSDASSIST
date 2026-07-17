package `in`.recoveriq.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Leave
import `in`.recoveriq.app.data.LeaveCreate
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.StatusChip
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.launch

@Composable
fun LeaveScreen(vm: AuthViewModel, user: User) {
    var refresh by remember { mutableIntStateOf(0) }
    var showApply by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val canApprove = user.isManager || user.isAdmin

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showApply = true },
                icon = { Icon(Icons.Filled.Add, null) },
                text = { Text("Apply") },
                containerColor = BrandBlue,
            )
        }
    ) { pad ->
        LazyColumn(
            Modifier.fillMaxSize().padding(pad).padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 12.dp, bottom = 90.dp),
        ) {
            item {
                AsyncContent(key = refresh, block = { vm.repo.leaveBalance() }) { bal, _ ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        bal.forEach { b ->
                            InfoCard(Modifier.weight(1f)) {
                                Text("${b.remaining ?: b.used}", fontWeight = FontWeight.Bold,
                                    color = BrandBlue, style = MaterialTheme.typography.titleMedium)
                                Text(b.type, style = MaterialTheme.typography.labelSmall, color = Muted)
                            }
                        }
                    }
                }
            }
            item { SectionTitle(if (canApprove) "Requests" else "My leave") }
            item {
                AsyncContent(key = refresh, block = { vm.repo.leaves() }) { leaves, _ ->
                    if (leaves.isEmpty()) EmptyState("No leave records.")
                    else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        leaves.forEach { lv ->
                            LeaveCard(lv, canApprove) { approve ->
                                scope.launch { runCatching { vm.repo.decideLeave(lv.id, approve) }; refresh++ }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showApply) ApplyLeaveDialog(
        onDismiss = { showApply = false },
        onConfirm = { body -> scope.launch { runCatching { vm.repo.applyLeave(body) }; showApply = false; refresh++ } },
    )
}

@Composable
private fun LeaveCard(lv: Leave, canApprove: Boolean, onDecide: (Boolean) -> Unit) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(lv.userName ?: (lv.leaveType ?: "Leave"), fontWeight = FontWeight.SemiBold)
                Text("${lv.leaveType} · ${lv.days} day${if (lv.days > 1) "s" else ""}",
                    style = MaterialTheme.typography.bodySmall, color = Muted)
                Text("${DateUtil.humanDate(lv.startDate)} → ${DateUtil.humanDate(lv.endDate)}",
                    style = MaterialTheme.typography.bodySmall, color = Muted)
                lv.reason?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Muted) }
            }
            StatusChip(lv.status)
        }
        if (canApprove && lv.status.equals("pending", true)) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { onDecide(true) }, modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = Good)) { Text("Approve") }
                OutlinedButton(onClick = { onDecide(false) }, modifier = Modifier.weight(1f)) { Text("Reject") }
            }
        }
    }
}

@Composable
private fun ApplyLeaveDialog(onDismiss: () -> Unit, onConfirm: (LeaveCreate) -> Unit) {
    val types = listOf("Casual", "Sick", "Earned", "Unpaid")
    var type by remember { mutableStateOf("Casual") }
    var startOffset by remember { mutableIntStateOf(0) }
    var days by remember { mutableIntStateOf(1) }
    var reason by remember { mutableStateOf("") }
    val startIso = DateUtil.plusDaysIso(startOffset)
    val endIso = DateUtil.plusDaysIso(startOffset + days - 1)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Apply for leave") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("Type", style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    types.forEach { t -> FilterChip(selected = type == t, onClick = { type = t }, label = { Text(t) }) }
                }
                Text("Start", style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("Today" to 0, "Tomorrow" to 1, "+7d" to 7).forEach { (l, o) ->
                        FilterChip(selected = startOffset == o, onClick = { startOffset = o }, label = { Text(l) })
                    }
                }
                Text("Days", style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(1, 2, 3, 5, 7).forEach { n ->
                        FilterChip(selected = days == n, onClick = { days = n }, label = { Text("$n") })
                    }
                }
                Text("${DateUtil.humanDate(startIso)} → ${DateUtil.humanDate(endIso)}",
                    style = MaterialTheme.typography.labelSmall, color = Muted)
                Fld(reason, "Reason (optional)") { reason = it }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onConfirm(LeaveCreate(leaveType = type, startDate = startIso, endDate = endIso, reason = reason.ifBlank { null }))
            }) { Text("Submit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
