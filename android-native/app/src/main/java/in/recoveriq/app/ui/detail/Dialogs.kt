package `in`.recoveriq.app.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.CallCreate
import `in`.recoveriq.app.ui.common.DatePickerField
import `in`.recoveriq.app.ui.common.DateUtil
import `in`.recoveriq.app.ui.theme.MutedDim

@Composable
fun PaymentDialog(maxAmount: Double, isCreditCard: Boolean, onDismiss: () -> Unit, onConfirm: (Double, String, String?) -> Unit) {
    var amount by remember { mutableStateOf(if (maxAmount > 0) "%.0f".format(maxAmount) else "") }
    var mode by remember { mutableStateOf("UPI") }
    var normStab by remember { mutableStateOf("STAB") }
    val amt = amount.toDoubleOrNull() ?: 0.0

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Record payment") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text("Amount (₹)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("Mode", style = MaterialTheme.typography.labelSmall, color = MutedDim)
                ChipRow(listOf("UPI", "Cash", "Bank", "Card", "Cheque"), mode) { mode = it }
                if (isCreditCard) {
                    Text("Paid at (credit card)", style = MaterialTheme.typography.labelSmall, color = MutedDim)
                    ChipRow(listOf("STAB", "NORM"), normStab) { normStab = it }
                }
            }
        },
        confirmButton = { TextButton(enabled = amt > 0, onClick = { onConfirm(amt, mode, if (isCreditCard) normStab else null) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun LogCallDialog(isCreditCard: Boolean, phonePtpOnly: Boolean = false,
                  onDismiss: () -> Unit, onConfirm: (CallCreate) -> Unit) {
    // Field officers logging a phone outcome can't book a payment (collections go through a field
    // visit), so PAID is removed from their disposition list — they can still record a phone PTP.
    val dispositions = if (phonePtpOnly)
        listOf("PTP", "RTP", "CALLBACK", "NO_CONTACT", "WRONG_NUMBER", "REFUSED")
    else listOf("PTP", "RTP", "PAID", "CALLBACK", "NO_CONTACT", "WRONG_NUMBER", "REFUSED")
    var disp by remember { mutableStateOf("PTP") }
    var amount by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var normStab by remember { mutableStateOf("STAB") }
    var dateIso by remember { mutableStateOf(DateUtil.plusDaysIso(1)) }

    val showAmount = disp == "PTP" || disp == "RTP" || (disp == "PAID" && !phonePtpOnly)
    val showDate = disp == "PTP" || disp == "RTP" || disp == "CALLBACK"
    val amt = amount.toDoubleOrNull() ?: 0.0

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (phonePtpOnly) "Log phone outcome" else "Log call outcome") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (phonePtpOnly) Text("Phone call before visit — record a promise-to-pay. Collections are booked from a field visit.",
                    style = MaterialTheme.typography.labelSmall, color = MutedDim)
                Text("Disposition", style = MaterialTheme.typography.labelSmall, color = MutedDim)
                ChipRow(dispositions, disp) { disp = it }

                if (showAmount) OutlinedTextField(
                    value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text(if (disp == "PAID") "Amount collected (₹)" else "Promised amount (₹)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (disp == "PAID" && isCreditCard) {
                    Text("Paid at (credit card)", style = MaterialTheme.typography.labelSmall, color = MutedDim)
                    ChipRow(listOf("STAB", "NORM"), normStab) { normStab = it }
                }

                if (showDate) {
                    Text(if (disp == "CALLBACK") "Call back on" else "Promised date",
                        style = MaterialTheme.typography.labelSmall, color = MutedDim)
                    DatePickerField("Pick date", dateIso) { dateIso = it }
                }

                OutlinedTextField(
                    value = note, onValueChange = { note = it }, label = { Text("Note (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onConfirm(
                    CallCreate(
                        caseId = 0, // filled by the caller
                        disposition = disp,
                        ptpAmount = if (disp == "PTP" || disp == "RTP") amt else 0.0,
                        ptpDate = if (disp == "PTP" || disp == "RTP") dateIso else null,
                        followUpDate = if (disp == "CALLBACK") dateIso else null,
                        paidAmount = if (disp == "PAID") amt else 0.0,
                        normStab = if (disp == "PAID" && isCreditCard) normStab else null,
                        note = note.ifBlank { null },
                    )
                )
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChipRow(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { opt ->
            FilterChip(selected = selected == opt, onClick = { onSelect(opt) }, label = { Text(opt) })
        }
    }
}

/** Chip row where each chip maps to a value (used for date presets). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChipRow(
    options: List<String>,
    selectedLabelFor: String,
    labelToValue: Map<String, String>,
    onSelect: (String) -> Unit,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { opt ->
            val value = labelToValue[opt] ?: opt
            FilterChip(
                selected = selectedLabelFor == value,
                onClick = { onSelect(value) },
                label = { Text(opt) },
            )
        }
    }
}
