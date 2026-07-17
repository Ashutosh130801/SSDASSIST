package `in`.recoveriq.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import `in`.recoveriq.app.data.Legal
import `in`.recoveriq.app.data.LegalCreate
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.StatusChip
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.Warn
import kotlinx.coroutines.launch

@Composable
fun LitigationScreen(vm: AuthViewModel) {
    var refresh by remember { mutableIntStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAdd = true },
                icon = { Icon(Icons.Filled.Add, null) },
                text = { Text("New matter") },
                containerColor = BrandBlue,
            )
        }
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(horizontal = 12.dp)) {
            AsyncContent(key = "ins$refresh", block = { vm.repo.legalInsights() }) { ins, _ ->
                Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Stat(Modifier.weight(1f), "Open", ins.open, BrandBlue)
                    Stat(Modifier.weight(1f), "Overdue", ins.hearingOverdue, Bad)
                    Stat(Modifier.weight(1f), "Today", ins.hearingToday, Warn)
                    Stat(Modifier.weight(1f), "This wk", ins.hearingWeek, Muted)
                }
            }
            AsyncContent(key = refresh, block = { vm.repo.legalCases() }) { cases, _ ->
                if (cases.isEmpty()) EmptyState("No litigation matters yet.")
                else LazyColumn(
                    Modifier.fillMaxSize().padding(top = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 90.dp),
                ) {
                    items(cases.size) { i ->
                        LegalCard(cases[i]) {
                            scope.launch { runCatching { vm.repo.deleteLegal(cases[i].id) }; refresh++ }
                        }
                    }
                }
            }
        }
    }

    if (showAdd) AddLegalDialog(
        onDismiss = { showAdd = false },
        onConfirm = { body -> scope.launch { runCatching { vm.repo.createLegal(body) }; showAdd = false; refresh++ } },
    )
}

@Composable
private fun Stat(modifier: Modifier, label: String, value: Int, color: androidx.compose.ui.graphics.Color) {
    InfoCard(modifier) {
        Text(value.toString(), fontWeight = FontWeight.Bold, color = color,
            style = MaterialTheme.typography.titleLarge)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Muted)
    }
}

@Composable
private fun LegalCard(l: Legal, onDelete: () -> Unit) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(l.borrowerName ?: l.matterType ?: "Legal matter", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(l.matterType, l.court, l.caseNumber).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
                l.nextHearingDate?.let {
                    Text("Next hearing: ${DateUtil.humanDate(it)}",
                        style = MaterialTheme.typography.bodySmall, color = Warn)
                }
                if (l.amount > 0) Text("₹${"%,.0f".format(l.amount)}",
                    style = MaterialTheme.typography.labelMedium, color = BrandBlue)
            }
            Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                StatusChip(l.status)
                IconButton(onClick = onDelete) { Icon(Icons.Filled.Delete, "Delete", tint = Bad) }
            }
        }
    }
}

@Composable
private fun AddLegalDialog(onDismiss: () -> Unit, onConfirm: (LegalCreate) -> Unit) {
    var borrower by remember { mutableStateOf("") }
    var matter by remember { mutableStateOf("") }
    var court by remember { mutableStateOf("") }
    var caseNo by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New litigation matter") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Fld(borrower, "Borrower name") { borrower = it }
                Fld(matter, "Matter type (e.g. Sec 138, Arbitration)") { matter = it }
                Fld(court, "Court") { court = it }
                Fld(caseNo, "Case number") { caseNo = it }
                Fld(amount, "Amount (₹)") { amount = it.filter { c -> c.isDigit() || c == '.' } }
            }
        },
        confirmButton = {
            TextButton(enabled = matter.isNotBlank(), onClick = {
                onConfirm(LegalCreate(
                    matterType = matter, borrowerName = borrower.ifBlank { null },
                    court = court.ifBlank { null }, caseNumber = caseNo.ifBlank { null },
                    amount = amount.toDoubleOrNull() ?: 0.0,
                ))
            }) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
internal fun Fld(value: String, label: String, onChange: (String) -> Unit) {
    OutlinedTextField(value = value, onValueChange = onChange, label = { Text(label) },
        singleLine = true, modifier = Modifier.fillMaxWidth())
}
