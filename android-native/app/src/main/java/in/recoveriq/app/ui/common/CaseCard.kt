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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.TextDark
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
fun PaidTag(paidStatus: String?) {
    val s = (paidStatus ?: "").uppercase()
    if (s.isBlank()) return
    val color = when { s == "PAID" -> Good; s == "PARTIAL" -> Warn; else -> Bad }
    TouchTag(s, color)
}

@Composable
fun TouchTag(text: String, color: Color) {
    Surface(color = color.copy(alpha = 0.15f), shape = RoundedCornerShape(6.dp)) {
        Text(
            text, color = color, style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
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
    val state = case.workState
    val cardColor = when (state) {
        "paid" -> Good.copy(alpha = 0.10f)
        "touched" -> Warn.copy(alpha = 0.12f)
        else -> CardWhite
    }
    val cardBorder = when {
        case.flagged == true -> Bad.copy(alpha = 0.7f)     // red caution — needs review
        state == "paid" -> Good.copy(alpha = 0.5f)
        state == "touched" -> Warn.copy(alpha = 0.5f)
        else -> GlassStroke
    }
    Surface(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        shape = RoundedCornerShape(16.dp),
        color = cardColor,
        contentColor = TextDark,
        border = BorderStroke(1.dp, cardBorder),
        shadowElevation = 5.dp,
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text((if (case.flagged == true) "⚠️ " else "") + (case.customerName ?: "Unnamed customer"),
                        fontWeight = FontWeight.Bold,
                        color = TextDark, style = MaterialTheme.typography.titleSmall)
                    // line 2: account · bank · product
                    Text(listOfNotNull(case.accountNo, case.bank, case.product).joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                    // line 3: bucket · cycle · area · pincode
                    val meta = listOfNotNull(
                        case.bucket?.let { "Bkt $it" }, case.cycle?.let { "cyc $it" },
                        case.team, case.pincode,
                    ).joinToString(" · ")
                    if (meta.isNotBlank()) Text(meta, style = MaterialTheme.typography.labelSmall, color = Muted)
                    // line 4: last disposition / remarks snippet
                    (case.disposition ?: case.remarks)?.takeIf { it.isNotBlank() }?.let {
                        Text("• ${it.take(48)}", style = MaterialTheme.typography.labelSmall, color = MutedDim)
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("₹${"%,.0f".format(case.pendingAmount)}", fontWeight = FontWeight.Bold, color = BrandBlue)
                    Text("of ₹${"%,.0f".format(if (case.enr > 0) case.enr else case.totalOutstanding)}",
                        style = MaterialTheme.typography.labelSmall, color = MutedDim)
                    if (case.receivedAmount > 0) Text("paid ₹${"%,.0f".format(case.receivedAmount)}",
                        style = MaterialTheme.typography.labelSmall, color = Good)
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(case.status)
                    PaidTag(case.paidStatus)
                    if (state == "paid") TouchTag("PAID", Good)
                    else if (state == "touched") TouchTag(if (case.visitedToday == true) "VISITED" else "DONE TODAY", Warn)
                    if (case.escalated == true) TouchTag("ESCALATED", Warn)
                    if (case.flagged == true) TouchTag("⚠ REVIEW", Bad)
                }
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
