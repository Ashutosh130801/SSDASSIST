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
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.data.UserCreate
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.Actions
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.EmptyState
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.launch

@Composable
fun TeamScreen(vm: AuthViewModel) {
    var refresh by remember { mutableIntStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAdd = true },
                icon = { Icon(Icons.Filled.Add, null) },
                text = { Text("Add member") },
                containerColor = BrandBlue,
            )
        }
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(horizontal = 12.dp)) {
            AsyncContent(key = refresh, block = { vm.repo.users() }) { users, _ ->
                if (users.isEmpty()) EmptyState("No team members.")
                else LazyColumn(
                    Modifier.fillMaxSize().padding(top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 90.dp),
                ) {
                    items(users.size) { i -> MemberCard(users[i]) }
                }
            }
        }
    }

    if (showAdd) AddMemberDialog(
        onDismiss = { showAdd = false },
        onConfirm = { body -> scope.launch { runCatching { vm.repo.createUser(body) }; showAdd = false; refresh++ } },
    )
}

@Composable
private fun MemberCard(u: User) {
    val context = LocalContext.current
    InfoCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(u.name, fontWeight = FontWeight.SemiBold)
                Text(u.email, style = MaterialTheme.typography.bodySmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.padding(top = 4.dp)) {
                    AssistChip(onClick = {}, label = { Text(u.roleLabel) })
                    u.branch?.let { AssistChip(onClick = {}, label = { Text(it) }) }
                }
            }
            if (!u.phone.isNullOrBlank())
                IconButton(onClick = { Actions.dial(context, u.phone) }) {
                    Icon(Icons.Filled.Call, "Call", tint = if (u.isActive) Good else Muted)
                }
        }
    }
}

@Composable
private fun AddMemberDialog(onDismiss: () -> Unit, onConfirm: (UserCreate) -> Unit) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var branch by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("telecaller") }
    val roles = listOf("telecaller", "fos", "manager", "admin")

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add team member") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Fld(name, "Full name") { name = it }
                Fld(email, "Work email") { email = it }
                Fld(phone, "Phone") { phone = it }
                Fld(password, "Temp password") { password = it }
                Fld(branch, "Branch") { branch = it }
                Text("Role", style = MaterialTheme.typography.labelSmall, color = Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    roles.forEach { r ->
                        FilterChip(selected = role == r, onClick = { role = r }, label = { Text(r) })
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && email.isNotBlank() && password.isNotBlank(), onClick = {
                onConfirm(UserCreate(
                    name = name, email = email.trim().lowercase(), password = password,
                    role = role, phone = phone.ifBlank { null }, branch = branch.ifBlank { null },
                ))
            }) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
