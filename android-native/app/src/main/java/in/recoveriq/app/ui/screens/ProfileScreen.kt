package `in`.recoveriq.app.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.recoveriq.app.data.EmployeeProfile
import `in`.recoveriq.app.data.Trends
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.common.TrendStrip
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.BrandBlueDark
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.TextDark
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import coil.compose.AsyncImage
import `in`.recoveriq.app.BuildConfig
import kotlinx.coroutines.launch

/** My E-ID — the employee's identity card, one-time self-edit of details, and change password. */
@Composable
fun ProfileScreen(vm: AuthViewModel, user: User) {
    var refresh by remember { mutableIntStateOf(0) }
    var showPwd by remember { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SectionTitle("My E-ID")

        // Field / calling / team-lead staff see their own FTD / MTD / LMTD / Overall achievement.
        if (user.isFieldAgent || user.isTelecaller || user.isTeamLead) {
            val trends by produceState<Trends?>(initialValue = null) {
                value = runCatching { vm.repo.myTrends().trends }.getOrNull()
            }
            trends?.let { t ->
                InfoCard { TrendStrip(t, title = "My cash collected — FTD / MTD / LMTD / Overall") }
            }
        }

        AsyncContent(key = refresh, block = { vm.repo.myProfile() }) { p, reload ->
            EidCard(p)

            PhotoUploadButton(vm) { refresh++; reload() }

            DetailsCard(p)

            val canEdit = !p.profileCompleted
            if (canEdit) {
                EditDetailsCard(vm, p) { refresh++; reload() }
            } else {
                InfoCard {
                    Text("Details locked", fontWeight = FontWeight.SemiBold)
                    Text(
                        "Your profile is complete. Contact HR / admin to change locked fields.",
                        style = MaterialTheme.typography.bodySmall, color = Muted,
                    )
                }
            }

            InfoCard {
                Text("Password", fontWeight = FontWeight.SemiBold)
                Text(
                    "Keep your account secure — change your password regularly.",
                    style = MaterialTheme.typography.bodySmall, color = Muted,
                )
                Spacer(Modifier.height(8.dp))
                OutlinedButton(
                    onClick = { showPwd = true }, modifier = Modifier.fillMaxWidth(),
                ) { Text("Change password") }
            }
        }
    }

    if (showPwd) {
        ChangePasswordDialog(vm, onDismiss = { showPwd = false })
    }
}

@Composable
private fun EidCard(p: EmployeeProfile) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = BrandBlue,
        contentColor = Color.White,
        shadowElevation = 8.dp,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .background(Brush.verticalGradient(listOf(BrandBlue, BrandBlueDark)))
                .padding(20.dp),
        ) {
            Text(
                "SSD ENTERPRISES",
                fontWeight = FontWeight.Bold, letterSpacing = 2.sp,
                style = MaterialTheme.typography.labelMedium, color = Color.White.copy(alpha = 0.85f),
            )
            Text(
                "Employee Identity Card",
                style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.7f),
            )
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                val photo = absPhotoUrl(p.photoUrl)
                Box(
                    Modifier.size(72.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f)),
                    contentAlignment = Alignment.Center,
                ) {
                    if (photo != null) {
                        AsyncImage(
                            model = photo, contentDescription = "Profile photo",
                            modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop,
                        )
                    } else {
                        Text(
                            initials(p.name),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold, color = Color.White,
                        )
                    }
                }
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        p.name, style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold, color = Color.White,
                    )
                    Text(
                        p.designation ?: roleTitle(p.role),
                        style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.9f),
                    )
                    p.empCode?.let {
                        Text(
                            it, style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold, color = Color.White,
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Row(Modifier.fillMaxWidth()) {
                EidField("Branch", p.branch ?: p.location ?: "—", Modifier.weight(1f))
                EidField("Blood Group", p.bloodGroup ?: "—", Modifier.weight(1f))
            }
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth()) {
                EidField("Phone", p.phone ?: "—", Modifier.weight(1f))
                EidField("Joined", p.joiningDate ?: "—", Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun EidField(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(
            label.uppercase(), style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.65f), letterSpacing = 1.sp,
        )
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Color.White, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun DetailsCard(p: EmployeeProfile) {
    InfoCard {
        Text("Details", fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        DetailRow("Email", p.email)
        DetailRow("Role", roleTitle(p.role))
        DetailRow("Location", p.location)
        DetailRow("Gender", p.gender)
        DetailRow("Date of birth", p.dob)
        DetailRow("Marital status", p.maritalStatus)
        DetailRow("Emergency contact", p.emergencyContact)
        DetailRow("Emergency name", p.emergencyName)
        DetailRow("Aadhaar", mask(p.aadharNumber))
        DetailRow("PAN", p.panNumber)
        DetailRow("Bank", p.bankName)
        DetailRow("Account", mask(p.bankAccount))
        DetailRow("IFSC", p.ifscCode)
        DetailRow("Address", p.currentAddress)
    }
}

@Composable
private fun DetailRow(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = MutedDim, modifier = Modifier.width(130.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, color = TextDark, modifier = Modifier.weight(1f))
    }
}

/**
 * Force dark input text on text fields in this screen. The app's default content
 * color here is white, which made typed characters invisible on the light field.
 */
@Composable
private fun darkFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = TextDark, unfocusedTextColor = TextDark,
    disabledTextColor = TextDark, cursorColor = BrandBlue,
    focusedBorderColor = BrandBlue, unfocusedBorderColor = Muted,
    focusedLabelColor = BrandBlue, unfocusedLabelColor = Muted,
)

@Composable
private fun EditDetailsCard(vm: AuthViewModel, p: EmployeeProfile, onSaved: () -> Unit) {
    val scope = rememberCoroutineScope()
    var phone by remember { mutableStateOf(p.phone ?: "") }
    var gender by remember { mutableStateOf(p.gender ?: "") }
    var dob by remember { mutableStateOf(p.dob ?: "") }
    var blood by remember { mutableStateOf(p.bloodGroup ?: "") }
    var marital by remember { mutableStateOf(p.maritalStatus ?: "") }
    var emgContact by remember { mutableStateOf(p.emergencyContact ?: "") }
    var emgName by remember { mutableStateOf(p.emergencyName ?: "") }
    var emgRel by remember { mutableStateOf(p.emergencyRelation ?: "") }
    var aadhar by remember { mutableStateOf(p.aadharNumber ?: "") }
    var pan by remember { mutableStateOf(p.panNumber ?: "") }
    var bankHolder by remember { mutableStateOf(p.bankHolder ?: "") }
    var bankAccount by remember { mutableStateOf(p.bankAccount ?: "") }
    var ifsc by remember { mutableStateOf(p.ifscCode ?: "") }
    var bankName by remember { mutableStateOf(p.bankName ?: "") }
    var address by remember { mutableStateOf(p.currentAddress ?: "") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }

    InfoCard {
        Text("Complete your profile", fontWeight = FontWeight.SemiBold)
        Text(
            "You can fill this once. Review carefully — it locks after saving.",
            style = MaterialTheme.typography.bodySmall, color = Muted,
        )
        Spacer(Modifier.height(8.dp))
        val fields = listOf<Pair<String, Pair<String, (String) -> Unit>>>(
            "Phone" to (phone to { v: String -> phone = v }),
            "Gender" to (gender to { v: String -> gender = v }),
            "Date of birth (YYYY-MM-DD)" to (dob to { v: String -> dob = v }),
            "Blood group" to (blood to { v: String -> blood = v }),
            "Marital status" to (marital to { v: String -> marital = v }),
            "Emergency contact" to (emgContact to { v: String -> emgContact = v }),
            "Emergency name" to (emgName to { v: String -> emgName = v }),
            "Emergency relation" to (emgRel to { v: String -> emgRel = v }),
            "Aadhaar number" to (aadhar to { v: String -> aadhar = v }),
            "PAN number" to (pan to { v: String -> pan = v }),
            "Bank account holder" to (bankHolder to { v: String -> bankHolder = v }),
            "Bank account number" to (bankAccount to { v: String -> bankAccount = v }),
            "IFSC code" to (ifsc to { v: String -> ifsc = v }),
            "Bank name" to (bankName to { v: String -> bankName = v }),
            "Current address" to (address to { v: String -> address = v }),
        )
        for ((label, pair) in fields) {
            OutlinedTextField(
                value = pair.first, onValueChange = pair.second,
                label = { Text(label) }, singleLine = label != "Current address",
                colors = darkFieldColors(),
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            )
        }
        msg?.let {
            Text(it, color = if (it.startsWith("Saved")) Good else MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
        Button(
            onClick = {
                scope.launch {
                    busy = true; msg = null
                    val patch = mapOf(
                        "phone" to phone, "gender" to gender, "dob" to dob,
                        "blood_group" to blood, "marital_status" to marital,
                        "emergency_contact" to emgContact, "emergency_name" to emgName,
                        "emergency_relation" to emgRel, "aadhar_number" to aadhar,
                        "pan_number" to pan, "bank_holder" to bankHolder,
                        "bank_account" to bankAccount, "ifsc_code" to ifsc,
                        "bank_name" to bankName, "current_address" to address,
                    ).filterValues { it.isNotBlank() }
                    val r = runCatching { vm.repo.updateMyProfile(patch) }
                    busy = false
                    if (r.isSuccess) { msg = "Saved."; onSaved() } else msg = "Could not save. Try again."
                }
            },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) { Text(if (busy) "Saving…" else "Save & lock") }
    }
}

@Composable
private fun ChangePasswordDialog(vm: AuthViewModel, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var current by remember { mutableStateOf("") }
    var next by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (done) "Password changed" else "Change password") },
        text = {
            if (done) {
                Text("Your password has been updated.")
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = current, onValueChange = { current = it },
                        label = { Text("Current password") }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        colors = darkFieldColors(),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = next, onValueChange = { next = it },
                        label = { Text("New password") }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        colors = darkFieldColors(),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = confirm, onValueChange = { confirm = it },
                        label = { Text("Confirm new password") }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        colors = darkFieldColors(),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    err?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                }
            }
        },
        confirmButton = {
            if (done) {
                TextButton(onClick = onDismiss) { Text("Done") }
            } else {
                Button(
                    enabled = !busy,
                    onClick = {
                        err = when {
                            next.length < 6 -> "New password must be at least 6 characters."
                            next != confirm -> "New passwords don't match."
                            next == current -> "New password must be different."
                            else -> null
                        }
                        if (err == null) scope.launch {
                            busy = true
                            val r = runCatching { vm.repo.changePassword(current, next) }
                            busy = false
                            if (r.isSuccess) done = true
                            else err = "Current password is incorrect."
                        }
                    },
                ) { Text(if (busy) "Saving…" else "Update") }
            }
        },
        dismissButton = if (done) null else ({ TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } }),
    )
}

/** First-login gate: forces a password change before the app is usable. */
@Composable
fun ForcePasswordChangeScreen(vm: AuthViewModel, onChanged: () -> Unit) {
    val scope = rememberCoroutineScope()
    var current by remember { mutableStateOf("") }
    var next by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(24.dp))
        Text("Set a new password", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(
            "For your security, please replace the starter password before continuing.",
            style = MaterialTheme.typography.bodyMedium, color = Muted, textAlign = TextAlign.Center,
        )
        OutlinedTextField(
            value = current, onValueChange = { current = it },
            label = { Text("Current (starter) password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            colors = darkFieldColors(), modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = next, onValueChange = { next = it },
            label = { Text("New password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            colors = darkFieldColors(), modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = confirm, onValueChange = { confirm = it },
            label = { Text("Confirm new password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            colors = darkFieldColors(), modifier = Modifier.fillMaxWidth(),
        )
        err?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        Button(
            enabled = !busy,
            onClick = {
                err = when {
                    next.length < 6 -> "New password must be at least 6 characters."
                    next != confirm -> "New passwords don't match."
                    next == current -> "New password must be different."
                    else -> null
                }
                if (err == null) scope.launch {
                    busy = true
                    val r = runCatching { vm.repo.changePassword(current, next) }
                    busy = false
                    if (r.isSuccess) onChanged() else err = "Current password is incorrect."
                }
            },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = BrandBlue),
        ) { Text(if (busy) "Saving…" else "Continue") }
    }
}

@Composable
private fun PhotoUploadButton(vm: AuthViewModel, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) scope.launch {
            busy = true
            val bytes = runCatching { ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
            busy = false
            if (bytes != null && runCatching { vm.repo.uploadProfilePhoto(bytes) }.isSuccess) onDone()
        }
    }
    OutlinedButton(onClick = { picker.launch("image/*") }, enabled = !busy) {
        Text(if (busy) "Uploading…" else "📷 Change photo")
    }
}

/** Make a stored photo ref absolute so Coil can load it (local refs come back as "/uploads/…"). */
private fun absPhotoUrl(u: String?): String? {
    if (u.isNullOrBlank()) return null
    return if (u.startsWith("http")) u else BuildConfig.BASE_URL.trimEnd('/') + u
}

private fun initials(name: String): String =
    name.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.take(2)
        .joinToString("") { it.first().uppercase() }.ifEmpty { "?" }

private fun mask(v: String?): String? {
    if (v.isNullOrBlank()) return v
    val s = v.trim()
    return if (s.length <= 4) s else "•••• " + s.takeLast(4)
}

private fun roleTitle(role: String): String = when (role) {
    "fos" -> "Field Executive"
    "telecaller" -> "Tele-caller"
    "teamlead" -> "Team Leader"
    "manager" -> "Manager"
    "headoffice" -> "Head Office"
    "hr" -> "HR"
    "it" -> "IT"
    "admin" -> "Administrator"
    else -> role.replaceFirstChar { it.uppercase() }
}
