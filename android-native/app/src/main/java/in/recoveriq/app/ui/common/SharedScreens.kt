package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Muted

@Composable
fun CasesScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize()) {
        SectionTitle("All cases", Modifier.padding(start = 16.dp, top = 12.dp))
        AsyncContent(block = { vm.repo.allCases() }) { cases, _ ->
            DataList(cases, emptyText = "No cases found.") { c -> CaseSummaryRow(c) }
        }
    }
}

@Composable
private fun CaseSummaryRow(c: Case) {
    InfoCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(c.customerName ?: "Unnamed", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(c.bank, c.branch, c.bucket).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                Text("₹${"%,.0f".format(c.pendingAmount)}", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                c.status?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = Muted) }
            }
        }
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
