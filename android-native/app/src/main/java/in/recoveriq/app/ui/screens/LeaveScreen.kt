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
import `in`.recoveriq.app.ui.common.DatePickerField
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
    val canApprove = user.isManager || user.isAdmin || user.role == "hr" || user.role == "headoffice"
    // Leave history (all employees) is an HR / manager function — admin is left out of it.
    val canSeeHistory = user.isManager || user.role == "hr" || user.role == "headoffice"
    // Leave history (all employees) filters.
    var histStatus by remember { mutableStateOf("all") }
    var histType by remember { mutableStateOf("all") }
    var histQ by remember { mutableStateOf("") }

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
            item { SectionTitle(if (canApprove) "Pending approvals" else "My leave") }
            item {
                AsyncContent(key = refresh, block = { vm.repo.leaves(status = if (canApprove) "pending" else null, scope = if (canApprove) "team" else "mine") }) { leaves, _ ->
                    if (leaves.isEmpty()) EmptyState(if (canApprove) "Nothing to approve." else "No leave records.")
                    else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        leaves.forEach { lv ->
                            LeaveCard(lv, canApprove && lv.userId != user.id) { approve ->
                                scope.launch { runCatching { vm.repo.decideLeave(lv.id, approve) }; refresh++ }
                            }
                        }
                    }
                }
            }
            if (!canApprove) {
                item { SectionTitle("My leave history") }
                item {
                    AsyncContent(key = refresh, block = { vm.repo.leaves(scope = "mine") }) { leaves, _ ->
                        if (leaves.isEmpty()) EmptyState("No leave records.")
                        else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            leaves.forEach { lv -> LeaveCard(lv, false) {} }
                        }
                    }
                }
            }
            if (canSeeHistory) {
                item { SectionTitle("Leave history — all employees") }
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            listOf("all" to "All", "pending" to "Pending", "approved" to "Approved", "rejected" to "Rejected").forEach { (v, l) ->
                                FilterChip(selected = histStatus == v, onClick = { histStatus = v }, label = { Text(l) })
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            (listOf("all" to "All types") + listOf("Casual", "Sick", "Earned", "Unpaid").map { it to it }).forEach { (v, l) ->
                                FilterChip(selected = histType == v, onClick = { histType = v }, label = { Text(l) })
                            }
                        }
                        Fld(histQ, "Search name, branch, type, reason") { histQ = it }
                    }
                }
                item {
                    AsyncContent(
                        key = "hist:$histStatus:$histType:$histQ:$refresh",
                        block = {
                            vm.repo.leaves(
                                status = histStatus.takeIf { it != "all" },
                                scope = "team",
                                leaveType = histType.takeIf { it != "all" },
                                q = histQ.ifBlank { null },
                            )
                        },
                    ) { leaves, _ ->
                        if (leaves.isEmpty()) EmptyState("No leave records match.")
                        else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            leaves.forEach { lv -> LeaveCard(lv, false) {} }
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
    var startIso by remember { mutableStateOf(DateUtil.plusDaysIso(0)) }
    var endIso by remember { mutableStateOf(DateUtil.plusDaysIso(0)) }
    var reason by remember { mutableStateOf("") }
    val days = DateUtil.daysInclusive(startIso, endIso)

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
                DatePickerField("Start date", startIso) { picked ->
                    startIso = picked
                    if ((DateUtil.millisFromIso(endIso) ?: 0) < (DateUtil.millisFromIso(picked) ?: 0)) endIso = picked
                }
                DatePickerField("End date", endIso) { picked ->
                    endIso = if ((DateUtil.millisFromIso(picked) ?: 0) < (DateUtil.millisFromIso(startIso) ?: 0)) startIso else picked
                }
                Text("Duration: $days day${if (days > 1) "s" else ""}",
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
