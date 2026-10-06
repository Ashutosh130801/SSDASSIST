package `in`.recoveriq.app.ui.fos

import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import `in`.recoveriq.app.data.DayVisit
import `in`.recoveriq.app.data.OfficerDayVisits
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.common.InfoCard
import `in`.recoveriq.app.ui.common.SectionTitle
import `in`.recoveriq.app.ui.theme.Bad
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.MutedDim
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Warn

private fun inr(v: Double) = "₹" + String.format("%,.0f", v)

/** FOS self-service: every case visit I logged today (time, outcome, collection, photo). */
@Composable
fun MyVisitsScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var data by remember { mutableStateOf<OfficerDayVisits?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        loading = true; error = null
        runCatching { vm.repo.myVisitsForDay() }
            .onSuccess { data = it }
            .onFailure { error = it.message ?: "Could not load your visits" }
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        SectionTitle("Today's Visits")
        val d = data
        if (d != null) {
            Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Stat("Visits", d.count.toString(), Modifier.weight(1f))
                Stat("Collected", inr(d.collected), Modifier.weight(1f), valueColor = Good)
            }
        }
        when {
            loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            error != null -> Box(Modifier.fillMaxSize(), Alignment.Center) { Text(error!!, color = Bad) }
            (d?.visits.isNullOrEmpty()) -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                Text("No visits logged today yet.", color = MutedDim)
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(d!!.visits) { v -> VisitRow(v, onOpenCase) }
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier = Modifier, valueColor: androidx.compose.ui.graphics.Color = TextDark) {
    Surface(modifier, color = CardWhite, shape = RoundedCornerShape(14.dp), shadowElevation = 1.dp) {
        Column(Modifier.padding(14.dp)) {
            Text(label, color = MutedDim, fontSize = 12.sp)
            Text(value, color = valueColor, fontWeight = FontWeight.Bold, fontSize = 20.sp)
        }
    }
}

@Composable
private fun VisitRow(v: DayVisit, onOpenCase: (Int) -> Unit) {
    InfoCard(Modifier.fillMaxWidth().clickable { onOpenCase(v.caseId) }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(v.customer ?: "—", fontWeight = FontWeight.SemiBold, color = TextDark)
                    Spacer(Modifier.width(8.dp))
                    Text(v.time, color = MutedDim, fontSize = 12.sp)
                }
                Text(
                    listOfNotNull(v.bank, v.product, v.account).joinToString(" · ").ifBlank { "—" },
                    color = Muted, fontSize = 12.5.sp
                )
                if (!v.address.isNullOrBlank()) Text(v.address!!, color = MutedDim, fontSize = 12.sp, maxLines = 2)
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    v.disposition?.takeIf { it.isNotBlank() }?.let { Chip(it, BrandBlue) }
                    if (v.paid && v.amount > 0) Chip("PAID " + inr(v.amount), Good)
                    v.normStab?.takeIf { it.isNotBlank() }?.let { Chip(it, Warn) }
                    if (v.personMoved) Chip("MOVED", Bad)
                    if (v.offLocation) Chip("OFF-LOCATION", Warn)
                }
                if (!v.note.isNullOrBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(v.note!!, color = Muted, fontSize = 12.5.sp)
                }
            }
            if (!v.photo.isNullOrBlank()) {
                Spacer(Modifier.width(10.dp))
                AsyncImage(
                    model = v.photo,
                    contentDescription = "Visit photo",
                    modifier = Modifier.size(64.dp).clip(RoundedCornerShape(10.dp))
                )
            }
        }
    }
}

@Composable
private fun Chip(text: String, color: androidx.compose.ui.graphics.Color) {
    Surface(color = color.copy(alpha = 0.12f), shape = RoundedCornerShape(8.dp)) {
        Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
    }
}
