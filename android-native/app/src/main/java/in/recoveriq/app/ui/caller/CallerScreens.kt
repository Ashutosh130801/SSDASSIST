package `in`.recoveriq.app.ui.caller

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DataList
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Muted

@Composable
fun CallQueueScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize()) {
        SectionTitle("Call queue", Modifier.padding(start = 16.dp, top = 12.dp))
        AsyncContent(block = { vm.repo.callQueue() }) { cases, _ ->
            DataList(cases, emptyText = "Your queue is empty.") { c -> CallRow(c) }
        }
    }
}

@Composable
fun PtpTrackerScreen(vm: AuthViewModel) {
    Column(Modifier.fillMaxSize()) {
        SectionTitle("Promise-to-pay tracker", Modifier.padding(start = 16.dp, top = 12.dp))
        AsyncContent(block = { vm.repo.ptpTracker() }) { cases, _ ->
            DataList(cases, emptyText = "No active promises to pay.") { c -> CallRow(c) }
        }
    }
}

@Composable
private fun CallRow(c: Case) {
    val context = LocalContext.current
    InfoCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(c.customerName ?: "Unnamed customer", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(c.bank, c.bucket, c.phone).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
                c.followUpDate?.let {
                    Text("Follow-up: $it", style = MaterialTheme.typography.bodySmall, color = Muted)
                }
                Text("Pending ₹${"%,.0f".format(c.pendingAmount)}",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
            }
            if (!c.phone.isNullOrBlank()) {
                IconButton(onClick = {
                    context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${c.phone}")))
                }) {
                    Icon(Icons.Filled.Call, contentDescription = "Call", tint = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}
