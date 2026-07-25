package `in`.recoveriq.app.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.data.TimelineEvent
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.Actions
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.StatusChip
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CaseDetailScreen(vm: AuthViewModel, user: User, caseId: Int, onBack: () -> Unit) {
    var refresh by remember { mutableIntStateOf(0) }
    var showPay by remember { mutableStateOf(false) }
    var showLogCall by remember { mutableStateOf(false) }
    var showVisit by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Case details") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = androidx.compose.ui.graphics.Color(0xF2FFFFFF),
                    titleContentColor = BrandBlue,
                    navigationIconContentColor = BrandBlue,
                ),
            )
        },
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
    ) { pad ->
        AsyncContent(key = refresh, modifier = Modifier.padding(pad), block = { vm.repo.case(caseId) }) { case, _ ->
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                CaseHeader(case)
                ActionBar(
                    case = case,
                    canPay = true,
                    canLogCall = user.isTelecaller || user.isAdmin || user.isManager,
                    canLogVisit = user.isFieldAgent,
                    onPay = { showPay = true },
                    onLogCall = { showLogCall = true },
                    onLogVisit = { showVisit = true },
                )
                DetailFields(case)

                SectionTitle("Activity log")
                AsyncContent(key = refresh, block = { vm.repo.timeline(caseId) }) { events, _ ->
                    if (events.isEmpty()) {
                        Text("No activity yet.", color = MutedDim)
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            events.forEach { TimelineRow(it) }
                        }
                    }
                }
                Spacer(Modifier.height(24.dp))
            }

            val isCC = case.segment == "Credit Card"
            if (showPay) {
                PaymentDialog(
                    maxAmount = case.pendingAmount,
                    isCreditCard = isCC,
                    onDismiss = { showPay = false },
                    onConfirm = { amount, mode, normStab ->
                        scope.launch {
                            runCatching { vm.repo.recordPayment(caseId, amount, mode, normStab = normStab) }
                            showPay = false; refresh++
                        }
                    },
                )
            }
            if (showLogCall) {
                LogCallDialog(
                    isCreditCard = isCC,
                    onDismiss = { showLogCall = false },
                    onConfirm = { call ->
                        scope.launch {
                            runCatching { vm.repo.logCall(call.copy(caseId = caseId)) }
                            showLogCall = false; refresh++
                        }
                    },
                )
            }
            if (showVisit) {
                LogVisitDialog(
                    isCreditCard = isCC,
                    onDismiss = { showVisit = false },
                    onConfirm = { v ->
                        scope.launch {
                            val ok = runCatching {
                                vm.repo.createVisit(
                                    caseId = caseId, lat = v.lat, lng = v.lng, accuracy = v.accuracy,
                                    personMoved = v.personMoved, paid = v.paid, amount = v.amount,
                                    disposition = v.disposition, note = v.note, photoJpeg = v.photoJpeg,
                                    normStab = v.normStab, ptpDate = v.ptpDate,
                                )
                            }.isSuccess
                            showVisit = false; refresh++
                            if (ok) {
                                // Send the agent a copy of the visit (photo + details) on their own WhatsApp.
                                Actions.shareVisitToSelf(context, user.phone, buildVisitMessage(case, user, v), v.photoJpeg)
                            }
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun CaseHeader(case: Case) {
    InfoCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Surface(color = BrandBlue.copy(alpha = 0.12f), shape = CircleShape) {
                Box(Modifier.size(46.dp), Alignment.Center) {
                    Text((case.customerName ?: "?").take(1).uppercase(),
                        color = BrandBlue, fontWeight = FontWeight.Bold)
                }
            }
            Column(Modifier.weight(1f)) {
                Text(case.customerName ?: "Unnamed customer",
                    style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(listOfNotNull(case.bank, case.product, case.bucket).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = Muted)
            }
            StatusChip(case.status)
        }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Amount("Pending", case.pendingAmount, BrandBlue)
            Amount("Received", case.receivedAmount, Good)
            Amount("Total", case.totalOutstanding, Muted)
        }
        if (case.propensity != null) {
            Spacer(Modifier.height(8.dp))
            Text("Recovery propensity: ${case.propensity}%", style = MaterialTheme.typography.labelMedium,
                color = if ((case.propensity ?: 0) >= 60) Good else Muted)
        }
    }
}

@Composable
private fun Amount(label: String, value: Double, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text("₹${"%,.0f".format(value)}", fontWeight = FontWeight.Bold, color = color)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MutedDim)
    }
}

@Composable
private fun ActionBar(
    case: Case, canPay: Boolean, canLogCall: Boolean, canLogVisit: Boolean,
    onPay: () -> Unit, onLogCall: () -> Unit, onLogVisit: () -> Unit,
) {
    val context = LocalContext.current
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ActionBtn("Call", Icons.Filled.Call, Modifier.weight(1f)) { Actions.dial(context, case.phone) }
        ActionBtn("WhatsApp", Icons.Filled.Chat, Modifier.weight(1f)) { Actions.whatsapp(context, case.phone) }
        ActionBtn("Navigate", Icons.Filled.Navigation, Modifier.weight(1f)) {
            Actions.navigate(context, case.latitude, case.longitude, case.customerName)
        }
    }
    Spacer(Modifier.height(4.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (canPay) Button(onClick = onPay, modifier = Modifier.weight(1f)) {
            Icon(Icons.Filled.Payments, null, Modifier.size(18.dp)); Spacer(Modifier.size(6.dp)); Text("Payment")
        }
        if (canLogCall) OutlinedButton(onClick = onLogCall, modifier = Modifier.weight(1f)) { Text("Log call") }
        if (canLogVisit) Button(onClick = onLogVisit, modifier = Modifier.weight(1f)) {
            Icon(Icons.Filled.PhotoCamera, null, Modifier.size(18.dp)); Spacer(Modifier.size(6.dp)); Text("Visit")
        }
    }
}

@Composable
private fun ActionBtn(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, null, Modifier.size(20.dp))
            Text(label, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun DetailFields(case: Case) {
    SectionTitle("Customer")
    InfoCard {
        Field("Name", case.customerName)
        Field("Phone", case.phone)
        Field("Alt phone", case.altPhone)
        Field("Card no", case.cardNo)
        Field("Account no", case.accountNo)
        Field("Address", case.address)
        Field("Pincode", case.pincode)
    }
    SectionTitle("Account")
    InfoCard {
        Field("Bank", case.bank)
        Field("Branch", case.branch)
        Field("Product", case.product)
        Field("Bucket", case.bucket)
        Field("Cycle", case.cycle)
        Field("Month", case.month)
        Field("Total outstanding", money(case.totalOutstanding))
        Field("Principal", money(case.principalOutstanding))
        Field("Min due", money(case.minAmountDue))
        Field("Funding target", money(case.fundingAmount))
        Field("Received", money(case.receivedAmount))
        Field("Pending", money(case.pendingAmount))
    }
    SectionTitle("Status")
    InfoCard {
        Field("Status", case.status)
        Field("Paid status", case.paidStatus)
        Field("Disposition", case.disposition)
        Field("Follow-up", case.followUpDate?.let { DateUtil.humanDate(it) })
        Field("Remarks", case.remarks)
        if (case.latitude != null && case.longitude != null)
            Field("Location", "${"%.5f".format(case.latitude)}, ${"%.5f".format(case.longitude)}")
    }
}

private fun money(v: Double): String? = if (v > 0.0) "₹${"%,.0f".format(v)}" else null

/** WhatsApp copy of a just-logged visit, sent to the agent's own number. */
private fun buildVisitMessage(case: Case, user: User, v: VisitDraft): String = buildString {
    appendLine("🧾 RecoverIQ — Field visit logged")
    appendLine("Customer: ${case.customerName ?: "—"}")
    case.phone?.let { appendLine("Phone: $it") }
    case.cardNo?.let { appendLine("Card no: $it") }
    case.accountNo?.let { appendLine("A/C no: $it") }
    val bankBits = listOfNotNull(case.bank, case.bucket)
    if (bankBits.isNotEmpty()) appendLine("Bank: ${bankBits.joinToString(" · ")}")
    case.address?.let { appendLine("Address: $it" + (case.pincode?.let { p -> ", $p" } ?: "")) }
    appendLine("Outcome: ${v.disposition ?: "—"}")
    if (v.paid && v.amount > 0) appendLine("Collected: ₹${"%,.0f".format(v.amount)}")
    if (v.personMoved) appendLine("⚠ Person has moved")
    v.note?.let { appendLine("Note: $it") }
    if (v.lat != null && v.lng != null) {
        appendLine("Location: ${"%.5f".format(v.lat)}, ${"%.5f".format(v.lng)}")
        appendLine("Map: https://maps.google.com/?q=${v.lat},${v.lng}")
    }
    append("Agent: ${user.name}")
}

@Composable
private fun Field(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MutedDim, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(0.4f))
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium,
            modifier = Modifier.weight(0.6f))
    }
}

@Composable
private fun TimelineRow(e: TimelineEvent) {
    val dotColor = when (e.type) {
        "payment" -> Good
        "visit" -> BrandBlue
        "call" -> androidx.compose.ui.graphics.Color(0xFFD97706)
        else -> MutedDim
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Surface(color = dotColor, shape = CircleShape, modifier = Modifier.size(10.dp).padding(top = 4.dp)) {}
        Column(Modifier.weight(1f)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(e.title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                Text(DateUtil.humanTime(e.at), style = MaterialTheme.typography.labelSmall, color = MutedDim)
            }
            if (!e.detail.isNullOrBlank())
                Text(e.detail, style = MaterialTheme.typography.bodySmall, color = Muted)
            if ((e.amount ?: 0.0) > 0.0)
                Text("₹${"%,.0f".format(e.amount)}", style = MaterialTheme.typography.labelMedium, color = Good)
            if (!e.by.isNullOrBlank())
                Text("by ${e.by}", style = MaterialTheme.typography.labelSmall, color = MutedDim)
        }
    }
}
