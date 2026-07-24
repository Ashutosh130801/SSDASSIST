package `in`.recoveriq.app.ui.detail

import android.annotation.SuppressLint
import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.google.android.gms.location.LocationServices
import `in`.recoveriq.app.ui.theme.Muted
import java.io.ByteArrayOutputStream

/** Result payload the caller uploads via Repository.createVisit(...). */
data class VisitDraft(
    val lat: Double?, val lng: Double?, val accuracy: Double?,
    val personMoved: Boolean, val paid: Boolean, val amount: Double,
    val disposition: String?, val note: String?, val photoJpeg: ByteArray?,
    val normStab: String? = null,
)

@OptIn(ExperimentalLayoutApi::class)
@SuppressLint("MissingPermission")
@Composable
fun LogVisitDialog(isCreditCard: Boolean, onDismiss: () -> Unit, onConfirm: (VisitDraft) -> Unit) {
    val context = LocalContext.current
    val dispositions = listOf("Met customer", "Not available", "Paid", "Wrong address", "Person moved", "PTP")
    var disp by remember { mutableStateOf("Met customer") }
    var paid by remember { mutableStateOf(false) }
    var moved by remember { mutableStateOf(false) }
    var amount by remember { mutableStateOf("") }
    var normStab by remember { mutableStateOf("STAB") }
    var note by remember { mutableStateOf("") }
    var photo by remember { mutableStateOf<Bitmap?>(null) }
    var lat by remember { mutableStateOf<Double?>(null) }
    var lng by remember { mutableStateOf<Double?>(null) }
    var acc by remember { mutableStateOf<Double?>(null) }

    // Grab the current location once when the dialog opens.
    androidx.compose.runtime.LaunchedEffect(Unit) {
        runCatching {
            LocationServices.getFusedLocationProviderClient(context).lastLocation
                .addOnSuccessListener { loc -> if (loc != null) { lat = loc.latitude; lng = loc.longitude; acc = loc.accuracy.toDouble() } }
        }
    }

    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicturePreview()) { bmp ->
        if (bmp != null) photo = bmp
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Log field visit") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(
                    if (lat != null) "Location captured ✓" else "Getting current location…",
                    style = MaterialTheme.typography.labelSmall, color = Muted,
                )
                Text("Outcome", style = MaterialTheme.typography.labelSmall, color = Muted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    dispositions.forEach { d ->
                        FilterChip(selected = disp == d, onClick = { disp = d }, label = { Text(d) })
                    }
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text("Payment collected"); Switch(checked = paid, onCheckedChange = { paid = it })
                }
                if (paid) OutlinedTextField(
                    value = amount, onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text("Amount (₹)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (paid && isCreditCard) {
                    Text("Paid at (credit card)", style = MaterialTheme.typography.labelSmall, color = Muted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("STAB", "NORM").forEach { o ->
                            FilterChip(selected = normStab == o, onClick = { normStab = o }, label = { Text(o) })
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text("Person has moved"); Switch(checked = moved, onCheckedChange = { moved = it })
                }
                OutlinedTextField(value = note, onValueChange = { note = it },
                    label = { Text("Note") }, modifier = Modifier.fillMaxWidth())

                photo?.let {
                    Image(it.asImageBitmap(), "Visit photo",
                        modifier = Modifier.fillMaxWidth().height(140.dp).padding(top = 4.dp))
                }
                OutlinedButton(onClick = { camera.launch(null) }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (photo == null) "Take photo" else "Retake photo")
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val jpeg = photo?.let { bmp ->
                    ByteArrayOutputStream().use { out -> bmp.compress(Bitmap.CompressFormat.JPEG, 80, out); out.toByteArray() }
                }
                onConfirm(VisitDraft(
                    lat = lat, lng = lng, accuracy = acc,
                    personMoved = moved, paid = paid,
                    amount = amount.toDoubleOrNull() ?: 0.0,
                    disposition = disp, note = note.ifBlank { null }, photoJpeg = jpeg,
                    normStab = if (paid && isCreditCard) normStab else null,
                ))
            }) { Text("Save visit") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
