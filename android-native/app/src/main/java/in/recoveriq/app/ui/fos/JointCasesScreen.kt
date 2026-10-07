package `in`.recoveriq.app.ui.fos

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.recoveriq.app.data.Case
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.TextDark

private fun inr0(v: Double?) = "₹" + String.format("%,.0f", v ?: 0.0)

/** FOS "Joint Cases": cases another FOS owns, sent to me for a new-address visit. I visit and
 *  collect; the case counts for me only once I log a paid visit (then it drops off this list). */
@Composable
fun JointCasesScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var rows by remember { mutableStateOf<List<Case>?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        loading = true; error = null
        runCatching { vm.repo.jointCases() }
            .onSuccess { rows = it }
            .onFailure { error = it.message ?: "Could not load joint cases" }
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        SectionTitle("Joint Cases")
        Text(
            "Cases another FOS owns, sent to you to visit a new address and collect. They count for you only after you log a paid visit.",
            color = MutedDim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 10.dp)
        )
        when {
            loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            error != null -> Box(Modifier.fillMaxSize(), Alignment.Center) { Text(error!!, color = Bad) }
            rows.isNullOrEmpty() -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                Text("No joint cases right now.", color = MutedDim)
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(rows!!) { c -> JointRow(c, onOpenCase) }
            }
        }
    }
}

@Composable
private fun JointRow(c: Case, onOpenCase: (Int) -> Unit) {
    Surface(
        Modifier.fillMaxWidth().clickable { onOpenCase(c.id) },
        color = CardWhite, shape = RoundedCornerShape(14.dp), shadowElevation = 1.dp
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(c.customerName ?: "—", color = TextDark, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                Text(inr0(c.pendingAmount), color = Bad, fontWeight = FontWeight.Bold)
            }
            Text("${c.bank ?: "—"} · ${c.product ?: "—"}", color = Muted, fontSize = 12.sp)
            c.fosName?.let { Text("Primary FOS: $it", color = MutedDim, fontSize = 12.sp) }
            c.jointNote?.takeIf { it.isNotBlank() }?.let {
                Text("📍 $it", color = BrandBlue, fontSize = 12.sp)
            }
        }
    }
}
