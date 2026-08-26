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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import `in`.recoveriq.app.ui.common.REVIEW_COLOR_NAMES
import `in`.recoveriq.app.ui.common.reviewColorOf
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Warn
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
            // Apply the Scaffold inset (pad) to the CONTENT too: AsyncContent only forwards the
            // modifier to its loading/error states, so without this the loaded header scrolls up
            // under the top bar. padding(pad) reserves the app-bar space; padding(16) is the gutter.
            Column(
                Modifier.fillMaxSize().padding(pad).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                CaseHeader(case)
                // Escalated cases are locked for the front-line FOS/caller (handled by their lead).
                val lockedForMe = case.escalated == true && (user.isFieldAgent || user.isTelecaller)
                if (lockedForMe) {
                    Surface(shape = RoundedCornerShape(12.dp), color = Bad.copy(alpha = 0.12f), contentColor = Bad) {
                        Text("🚩 Escalated — locked. Your team lead / manager is handling this case.",
                            modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold)
                    }
                }
                ActionBar(
                    case = case,
                    meId = user.id,
                    canPay = !lockedForMe,
                    canLogCall = !lockedForMe && (user.isTelecaller || user.isAdmin || user.isManager),
                    canLogVisit = !lockedForMe && user.isFieldAgent,
                    onPay = { showPay = true },
                    onLogCall = { showLogCall = true },
                    onLogVisit = { showVisit = true },
                )
                // Personal colour highlight — flag to review later (only you see your colours).
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("🔖 Highlight:", color = Muted, style = MaterialTheme.typography.labelMedium)
                    REVIEW_COLOR_NAMES.forEach { col ->
                        val c = reviewColorOf(col)!!
                        val selected = case.reviewColor == col
                        Surface(color = c, shape = CircleShape,
                            border = if (selected) BorderStroke(3.dp, TextDark) else BorderStroke(1.dp, GlassStroke),
                            modifier = Modifier.size(24.dp).clickable {
                                scope.launch { runCatching { vm.repo.setReviewFlag(caseId, if (selected) null else col) }; refresh++ }
                            }) {}
                    }
                }

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
                    agentName = user.name,
                    caseLabel = "Case #${case.id}" + (case.customerName?.let { " • $it" } ?: ""),
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
                                // Open WhatsApp's contact picker so the agent can forward the
                                // visit summary + geotagged photo to anyone (office/colleague/self).
                                Actions.shareVisit(context, buildVisitMessage(case, user, v), v.photoJpeg)
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
        // CC & PL/BL sheets have no FUNDING AMOUNT, so base pending on TOS (then ENR) — never negative.
        val payBase = if (case.fundingAmount > 0) case.fundingAmount
            else if (case.totalOutstanding > 0) case.totalOutstanding else case.enr
        val pend = (payBase - case.receivedAmount).coerceAtLeast(0.0)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Amount("Pending", pend, BrandBlue)
            Amount("Received", case.receivedAmount, Good)
            Amount(if (case.fundingAmount > 0) "Funded" else "Outstanding", payBase, Muted)
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
    case: Case, meId: Int, canPay: Boolean, canLogCall: Boolean, canLogVisit: Boolean,
    onPay: () -> Unit, onLogCall: () -> Unit, onLogVisit: () -> Unit,
) {
    val context = LocalContext.current
    var showCallChoice by remember { mutableStateOf(false) }
    if (showCallChoice) {
        AlertDialog(
            onDismissRequest = { showCallChoice = false },
            title = { Text("Place the call") },
            text = { Text("Call ${case.customerName ?: "this customer"} through Zoiper (recommended) or your phone dialer?") },
            confirmButton = {
                TextButton(onClick = { showCallChoice = false; Actions.dialViaZoiper(context, case.phone) }) { Text("Call via Zoiper") }
            },
            dismissButton = {
                TextButton(onClick = { showCallChoice = false; Actions.dial(context, case.phone) }) { Text("Phone dialer") }
            },
        )
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ActionBtn("Call", Icons.Filled.Call, Modifier.weight(1f)) { showCallChoice = true }
        ActionBtn("WhatsApp", Icons.Filled.Chat, Modifier.weight(1f)) { Actions.whatsapp(context, case.phone) }
        ActionBtn("Navigate", Icons.Filled.Navigation, Modifier.weight(1f)) {
            Actions.navigate(context, case.latitude, case.longitude, case.customerName)
        }
    }
    // Contact the case's assigned field agent / caller (team lead & callers use this).
    val showFos = !case.assignedFosPhone.isNullOrBlank() && case.assignedFosId != meId
    val showCaller = !case.assignedCallerPhone.isNullOrBlank() && case.assignedCallerId != meId
    if (showFos || showCaller) {
        Spacer(Modifier.height(4.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (showFos) ActionBtn("Call FOS", Icons.Filled.Call, Modifier.weight(1f)) { Actions.dial(context, case.assignedFosPhone) }
            if (showCaller) ActionBtn("Call caller", Icons.Filled.Call, Modifier.weight(1f)) { Actions.dial(context, case.assignedCallerPhone) }
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
    val ctx = LocalContext.current
    // Latest address / phone a caller or head-office found mid-cycle — highlighted for the FOS.
    if (!case.newPhone.isNullOrBlank() || !case.newAddress.isNullOrBlank()) {
        SectionTitle("🆕 Latest customer contact")
        InfoCard {
            if (!case.newContactBy.isNullOrBlank())
                Text("Updated by ${case.newContactBy}", style = MaterialTheme.typography.labelSmall, color = MutedDim)
            if (!case.newPhone.isNullOrBlank()) {
                Text("📞 ${case.newPhone}", fontWeight = FontWeight.SemiBold, color = BrandBlue)
                Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { Actions.dial(ctx, case.newPhone) }) { Text("Call") }
                    OutlinedButton(onClick = { Actions.whatsapp(ctx, case.newPhone) }) { Text("WhatsApp") }
                }
            }
            if (!case.newAddress.isNullOrBlank()) {
                Spacer(Modifier.height(8.dp))
                Text("📍 ${case.newAddress}")
                OutlinedButton(onClick = { Actions.mapsSearch(ctx, case.newAddress) }, modifier = Modifier.padding(top = 4.dp)) { Text("Navigate") }
            }
        }
    }
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
        if (case.fundingAmount > 0) Field("Funding target", money(case.fundingAmount))
        Field("Received", money(case.receivedAmount))
        val base = if (case.fundingAmount > 0) case.fundingAmount
            else if (case.totalOutstanding > 0) case.totalOutstanding else case.enr
        Field("Pending", money((base - case.receivedAmount).coerceAtLeast(0.0)))
    }
    SectionTitle("Recovery (MIS)")
    InfoCard {
        Field("Segment", case.segment)
        Field("ENR", if (case.enr > 0) money(case.enr) else null)
        Field("NORM amount", if (case.normAmount > 0) money(case.normAmount) else null)
        Field("STAB amount", if (case.stabAmount > 0) money(case.stabAmount) else null)
        Field("Paid at (NORM/STAB)", case.normStab)
        Field("Caller", case.callerName)
        Field("Field agent (FOS)", case.fosName)
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

/** WhatsApp caption for a just-logged visit — shared (with the geotagged photo) to anyone the agent picks. */
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
    val fresh = run {
        val ms = try { DateUtil.millisFromIso(e.at) ?: 0L } catch (ex: Exception) { 0L }
        ms > 0L && System.currentTimeMillis() - ms < 24L * 3600 * 1000
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = if (fresh) Modifier.background(Warn.copy(alpha = 0.12f), RoundedCornerShape(8.dp)).padding(6.dp) else Modifier) {
        Surface(color = dotColor, shape = CircleShape, modifier = Modifier.size(10.dp).padding(top = 4.dp)) {}
        Column(Modifier.weight(1f)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(e.title + (if (fresh) "  🆕" else ""), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
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
