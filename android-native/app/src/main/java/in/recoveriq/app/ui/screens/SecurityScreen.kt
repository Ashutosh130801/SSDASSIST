package `in`.recoveriq.app.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.TwoFASetup
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.AsyncContent
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.Qr
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.launch

@Composable
fun SecurityScreen(vm: AuthViewModel, user: User) {
    var refresh by remember { mutableIntStateOf(0) }
    var setup by remember { mutableStateOf<TwoFASetup?>(null) }
    var otp by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SectionTitle("Security")
        InfoCard {
            Text(user.name, fontWeight = FontWeight.SemiBold)
            Text(user.email, style = MaterialTheme.typography.bodySmall, color = Muted)
            Text(user.roleLabel, style = MaterialTheme.typography.bodySmall, color = Muted)
        }

        AsyncContent(key = refresh, block = { vm.repo.twoFAStatus() }) { status, _ ->
            InfoCard {
                Text("Two-factor authentication", fontWeight = FontWeight.SemiBold)
                Text(
                    if (status.enabled) "Enabled — your account asks for a code at sign-in."
                    else "Add an authenticator app for an extra layer of security.",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (status.enabled) Good else Muted,
                )
                Spacer(Modifier.height(8.dp))

                if (status.enabled) {
                    OutlinedTextField(
                        value = otp, onValueChange = { otp = it.filter { c -> c.isDigit() }.take(6) },
                        label = { Text("Current 6-digit code") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = {
                            scope.launch {
                                val r = runCatching { vm.repo.twoFADisable(otp) }
                                msg = if (r.isSuccess) "2FA disabled." else "Incorrect code."
                                otp = ""; refresh++
                            }
                        },
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Bad),
                    ) { Text("Disable 2FA") }
                } else if (setup == null) {
                    Button(
                        onClick = { scope.launch { setup = runCatching { vm.repo.twoFASetup() }.getOrNull() } },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Set up 2FA") }
                } else {
                    Text("1. Scan this QR in Google Authenticator (or enter the key).",
                        style = MaterialTheme.typography.bodySmall, color = Muted)
                    val qr = remember(setup) { Qr.bitmap(setup!!.otpauthUrl) }
                    if (qr != null) {
                        Image(qr, contentDescription = "2FA QR",
                            modifier = Modifier.size(200.dp).padding(vertical = 8.dp)
                                .align(Alignment.CenterHorizontally))
                    }
                    Text("Key: ${setup!!.secret}", style = MaterialTheme.typography.labelSmall, color = Muted)
                    OutlinedTextField(
                        value = otp, onValueChange = { otp = it.filter { c -> c.isDigit() }.take(6) },
                        label = { Text("2. Enter the 6-digit code") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                    Button(
                        onClick = {
                            scope.launch {
                                val r = runCatching { vm.repo.twoFAEnable(otp) }
                                if (r.isSuccess) { msg = "2FA enabled."; setup = null; otp = ""; refresh++ }
                                else msg = "Incorrect code — try again."
                            }
                        },
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    ) { Text("Verify & enable") }
                    OutlinedButton(onClick = { setup = null; otp = "" },
                        modifier = Modifier.fillMaxWidth()) { Text("Cancel") }
                }
                msg?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Good, modifier = Modifier.padding(top = 8.dp)) }
            }
        }
    }
}
