package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Muted

private val STATUS_FILTERS = listOf("All", "new", "ptp", "callback", "paid")

@Composable
fun CasesScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var search by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("All") }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        SectionTitle("All cases", Modifier.padding(top = 12.dp, start = 4.dp))
        OutlinedTextField(
            value = search, onValueChange = { search = it },
            placeholder = { Text("Search name, account, phone, pincode") },
            leadingIcon = { Icon(Icons.Filled.Search, null) },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        FilterChipsRow(STATUS_FILTERS, status) { status = it }
        Spacer(Modifier.height(8.dp))
        AsyncContent(key = "$search|$status", block = {
            vm.repo.allCases(status = status.takeIf { it != "All" }, search = search)
        }) { cases, _ ->
            if (cases.isEmpty()) {
                EmptyState("No matching cases.")
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp)) {
                    items(cases.size) { i -> CaseCard(cases[i], onClick = { onOpenCase(cases[i].id) }) }
                }
            }
        }
    }
}

@Composable
fun FilterChipsRow(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
        options.forEach { opt ->
            FilterChip(
                selected = selected == opt,
                onClick = { onSelect(opt) },
                label = { Text(opt.replaceFirstChar { it.uppercase() }) },
            )
        }
    }
}

@Composable
fun EmptyState(text: String) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center,
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun ProfileScreen(vm: AuthViewModel, user: User) {
    Column(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(user.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(user.roleLabel, color = Muted)
        InfoCard {
            ProfileRow("Email", user.email)
            user.phone?.let { ProfileRow("Phone", it) }
            user.branch?.let { ProfileRow("Branch", it) }
            if (user.banks.isNotEmpty()) ProfileRow("Banks", user.banks.joinToString(", "))
        }
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = { vm.logout() },
            modifier = Modifier.fillMaxWidth().height(48.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Bad),
        ) { Text("Sign out") }
    }
}

@Composable
private fun ProfileRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Muted, style = MaterialTheme.typography.bodySmall)
        Text(value, fontWeight = FontWeight.Medium, style = MaterialTheme.typography.bodyMedium)
    }
}
