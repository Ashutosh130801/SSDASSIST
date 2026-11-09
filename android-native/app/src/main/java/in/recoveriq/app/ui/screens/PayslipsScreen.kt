package `in`.recoveriq.app.ui.screens

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private fun rupees(v: Any?): String = "₹" + "%,.2f".format((v as? Number)?.toDouble() ?: 0.0)

/** Save a PDF from the server to the cache and open it (or offer to share it). */
private suspend fun openPdf(ctx: Context, name: String, fetch: suspend () -> okhttp3.ResponseBody): String? = try {
    val file = withContext(Dispatchers.IO) {
        val body = fetch()
        val f = java.io.File(ctx.cacheDir, name)
        f.outputStream().use { out -> body.byteStream().use { it.copyTo(out) } }
        f
    }
    val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", file)
    val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/pdf")
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        ctx.startActivity(view)
    } catch (e: Exception) {
        val share = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, uri)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(share, name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    null
} catch (e: Exception) {
    e.message ?: "Could not open the PDF"
}

/** My Payslips: released payslips (PDF) + this year's income-tax summary and statement. */
@Composable
fun PayslipsScreen(vm: AuthViewModel) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var slips by remember { mutableStateOf<List<Map<String, Any?>>?>(null) }
    var tax by remember { mutableStateOf<Map<String, Any?>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<Int?>(null) }
    LaunchedEffect(Unit) {
        runCatching { vm.repo.myPayslips() }.onSuccess { slips = it }.onFailure { error = it.message; slips = emptyList() }
        runCatching { vm.repo.myTax() }.onSuccess { tax = it }
    }
    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(top = 12.dp, bottom = 40.dp),
    ) {
        item { SectionTitle("My Payslips") }
        error?.let { e -> item { Text(e, color = Bad) } }
        val list = slips
        if (list == null) {
            item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() } }
        } else if (list.isEmpty()) {
            item { Text("No payslips released yet.", color = Muted) }
        } else {
            items(list) { p ->
                val id = (p["line_id"] as? Number)?.toInt() ?: 0
                val paid = p["pay_status"] == "paid"
                InfoCard {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(p["label"]?.toString() ?: "", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.titleMedium)
                            Text(rupees(p["net"]), fontWeight = FontWeight.Bold, color = Good, style = MaterialTheme.typography.titleMedium)
                        }
                        Text("Gross ${rupees(p["gross"])} · Deductions ${rupees(p["deductions"])}", color = Muted,
                            style = MaterialTheme.typography.bodySmall)
                        Text(if (p["hold"] == true) "On hold" else if (paid) "Paid ${p["paid_on"] ?: ""}" else "Processed",
                            color = if (p["hold"] == true) Bad else if (paid) Good else BrandBlue, style = MaterialTheme.typography.labelMedium)
                        Button(onClick = {
                            busy = id
                            scope.launch {
                                error = openPdf(ctx, "Payslip_${p["period"]}.pdf") { vm.repo.myPayslipPdf(id) }
                                busy = null
                            }
                        }, enabled = busy == null, colors = ButtonDefaults.buttonColors(containerColor = BrandBlue)) {
                            Text(if (busy == id) "Opening…" else "View / download PDF")
                        }
                    }
                }
            }
        }
        val t = tax
        val proj = t?.get("projection") as? Map<*, *>
        if (t != null && proj != null) {
            item { SectionTitle("My income tax — FY ${t["fy"]}") }
            item {
                val annual = proj["annual"] as? Map<*, *>
                InfoCard {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Regime: ${proj["regime"]}", fontWeight = FontWeight.SemiBold)
                        Text("Projected taxable income ${rupees(annual?.get("taxable"))}", style = MaterialTheme.typography.bodySmall)
                        Text("Tax for the year ${rupees(annual?.get("total"))}", style = MaterialTheme.typography.bodySmall)
                        Text("TDS so far ${rupees(proj["tds_so_far"])} · per month now ${rupees(proj["monthly_tds"])}",
                            color = Muted, style = MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick = {
                            scope.launch { error = openPdf(ctx, "Tax_Statement_FY${t["fy"]}.pdf") { vm.repo.myForm16(t["fy"]?.toString()) } }
                        }) { Text("Tax statement (PDF)") }
                        Text("Change your regime or investment declarations on the web: My Payslips → My income tax.",
                            color = Muted, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
