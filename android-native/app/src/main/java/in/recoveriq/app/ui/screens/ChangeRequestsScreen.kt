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
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import kotlinx.coroutines.launch

/** HR / Admin: review employees' profile change requests — approve (applies) or reject. */
@Composable
fun ChangeRequestsScreen(vm: AuthViewModel) {
    val scope = rememberCoroutineScope()
    var refresh by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf("pending") }
    var query by remember { mutableStateOf("") }
    val notes = remember { mutableStateMapOf<Int, String>() }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 12.dp, bottom = 24.dp),
    ) {
        item { SectionTitle("Profile Change Requests") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("pending" to "Pending", "approved" to "Approved", "rejected" to "Rejected", "all" to "All").forEach { (v, l) ->
                    FilterChip(selected = status == v, onClick = { status = v }, label = { Text(l) })
                }
            }
        }
        item { Fld(query, "Search name, field, value") { query = it } }
        item {
            AsyncContent(
                key = "$status:$query:$refresh",
                block = { vm.repo.changeRequests(status.takeIf { it != "all" }, query.ifBlank { null }) },
            ) { reqs, _ ->
                if (reqs.isEmpty()) EmptyState("No requests.")
                else Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    reqs.forEach { r ->
                        InfoCard {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Column(Modifier.weight(1f)) {
                                    Text(r.userName ?: "Employee", fontWeight = FontWeight.SemiBold, color = TextDark)
                                    Text(
                                        listOfNotNull(r.userCode, r.userBranch).joinToString(" · "),
                                        style = MaterialTheme.typography.labelSmall, color = Muted,
                                    )
                                }
                                val col = when (r.status) { "approved" -> Good; "rejected" -> MaterialTheme.colorScheme.error; else -> BrandBlue }
                                Text(r.status.uppercase(), style = MaterialTheme.typography.labelSmall, color = col, fontWeight = FontWeight.SemiBold)
                            }
                            Text(
                                "${r.fieldLabel ?: r.field}:  ${r.oldValue ?: "—"}  →  ${r.newValue ?: ""}",
                                style = MaterialTheme.typography.bodyMedium, color = TextDark,
                                modifier = Modifier.padding(top = 6.dp),
                            )
                            if (!r.note.isNullOrBlank()) Text("Reason: ${r.note}", style = MaterialTheme.typography.bodySmall, color = Muted)
                            if (r.status == "pending") {
                                Fld(notes[r.id] ?: "", "Remark (optional)") { notes[r.id] = it }
                                Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(
                                        onClick = { scope.launch { runCatching { vm.repo.decideChangeRequest(r.id, true, notes[r.id]) }; notes.remove(r.id); refresh++ } },
                                        modifier = Modifier.weight(1f),
                                        colors = ButtonDefaults.buttonColors(containerColor = Good),
                                    ) { Text("Approve & apply") }
                                    OutlinedButton(
                                        onClick = { scope.launch { runCatching { vm.repo.decideChangeRequest(r.id, false, notes[r.id]) }; notes.remove(r.id); refresh++ } },
                                        modifier = Modifier.weight(1f),
                                    ) { Text("Reject") }
                                }
                            } else if (!r.reviewerName.isNullOrBlank() || !r.reviewNote.isNullOrBlank()) {
                                Text(
                                    listOfNotNull(
                                        r.reviewerName?.let { "by $it" },
                                        r.reviewNote,
                                    ).joinToString(" · "),
                                    style = MaterialTheme.typography.labelSmall, color = Muted,
                                    modifier = Modifier.padding(top = 4.dp),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
