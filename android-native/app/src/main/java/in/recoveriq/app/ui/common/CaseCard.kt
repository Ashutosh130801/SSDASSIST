package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.Warn

@Composable
fun StatusChip(status: String?) {
    val s = (status ?: "new").lowercase()
    val color = when {
        s.contains("paid") || s.contains("resolved") -> Good
        s.contains("ptp") || s.contains("callback") -> Warn
        else -> BrandBlue
    }
    Surface(color = color.copy(alpha = 0.12f), shape = RoundedCornerShape(6.dp)) {
        Text(
            (status ?: "New").replaceFirstChar { it.uppercase() },
            color = color, style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
        )
    }
}

@Composable
fun CaseCard(
    case: Case,
    onClick: () -> Unit,
    showQuickActions: Boolean = true,
    subtitle: String? = null,
) {
    val context = LocalContext.current
    Surface(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        shape = RoundedCornerShape(16.dp),
        color = CardWhite,
        border = BorderStroke(1.dp, GlassStroke),
        shadowElevation = 5.dp,
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text(case.customerName ?: "Unnamed customer", fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface)
                    Text(
                        subtitle ?: listOfNotNull(case.bank, case.bucket, case.pincode).joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall, color = Muted,
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("₹${"%,.0f".format(case.pendingAmount)}", fontWeight = FontWeight.Bold,
                        color = BrandBlue)
                    Text("of ₹${"%,.0f".format(case.totalOutstanding)}",
                        style = MaterialTheme.typography.labelSmall, color = MutedDim)
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StatusChip(case.status)
                if (showQuickActions && !case.phone.isNullOrBlank()) {
                    Row {
                        IconButton(onClick = { Actions.dial(context, case.phone) }, modifier = Modifier.size(34.dp)) {
                            Icon(Icons.Filled.Call, "Call", tint = BrandBlue)
                        }
                        IconButton(onClick = { Actions.whatsapp(context, case.phone) }, modifier = Modifier.size(34.dp)) {
                            Icon(Icons.Filled.Chat, "WhatsApp", tint = Good)
                        }
                    }
                }
            }
        }
    }
}
