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
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
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
import `in`.recoveriq.app.data.Template
import `in`.recoveriq.app.data.TemplateCreate
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.launch

@Composable
fun CommunicationScreen(vm: AuthViewModel) {
    var refresh by remember { mutableIntStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAdd = true },
                icon = { Icon(Icons.Filled.Add, null) },
                text = { Text("New template") },
                containerColor = BrandBlue,
            )
        }
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(horizontal = 12.dp)) {
            AsyncContent(key = refresh, block = { vm.repo.templates() }) { templates, _ ->
                if (templates.isEmpty()) EmptyState("No message templates yet.")
                else LazyColumn(
                    Modifier.fillMaxSize().padding(top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 90.dp),
                ) {
                    items(templates.size) { i ->
                        TemplateCard(templates[i]) {
                            scope.launch { runCatching { vm.repo.deleteTemplate(templates[i].id) }; refresh++ }
                        }
                    }
                }
            }
        }
    }

    if (showAdd) AddTemplateDialog(
        onDismiss = { showAdd = false },
        onConfirm = { body -> scope.launch { runCatching { vm.repo.createTemplate(body) }; showAdd = false; refresh++ } },
    )
}

@Composable
private fun TemplateCard(t: Template, onDelete: () -> Unit) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(t.name, fontWeight = FontWeight.SemiBold)
                AssistChip(onClick = {}, label = { Text(t.channel) },
                    modifier = Modifier.padding(vertical = 4.dp))
                Text(t.body, style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            IconButton(onClick = onDelete) { Icon(Icons.Filled.Delete, "Delete", tint = Bad) }
        }
    }
}

@Composable
private fun AddTemplateDialog(onDismiss: () -> Unit, onConfirm: (TemplateCreate) -> Unit) {
    var name by remember { mutableStateOf("") }
    var channel by remember { mutableStateOf("whatsapp") }
    var body by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New template") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Fld(name, "Template name") { name = it }
                Text("Channel", style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("whatsapp", "sms").forEach { c ->
                        FilterChip(selected = channel == c, onClick = { channel = c }, label = { Text(c) })
                    }
                }
                OutlinedTextField(value = body, onValueChange = { body = it },
                    label = { Text("Message body") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && body.isNotBlank(), onClick = {
                onConfirm(TemplateCreate(name = name, channel = channel, body = body))
            }) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
