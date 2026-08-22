package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.shape.RoundedCornerShape
import `in`.recoveriq.app.data.PerfLeaderRow
import `in`.recoveriq.app.data.PerfPortfolio
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Warn

private fun rupee(v: Double) = "₹" + "%,.0f".format(v)

/**
 * The signed-in FOS/caller's OWN scorecard — per-portfolio achievement + the portfolio-wise
 * leaderboard (peers on the same portfolio ranked by paid %, with the viewer's row highlighted),
 * kept separate per month. Mirrors the web "My Performance → My scorecard".
 */
@Composable
fun MyPerformanceScreen(vm: AuthViewModel, user: User) {
    var mb by remember { mutableStateOf("current") }
    val live = rememberLiveKey()
    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        SectionTitle("My Performance", Modifier.padding(top = 12.dp, start = 4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("current" to "This month", "next" to "Next month", "" to "All months").forEach { (v, l) ->
                FilterChip(selected = mb == v, onClick = { mb = v }, label = { Text(l) })
            }
        }
        Text(
            "Each portfolio is kept separate for the month you pick — nothing is merged.",
            color = Muted, style = MaterialTheme.typography.labelSmall,
        )
        AsyncContent(key = "$mb|$live", block = { vm.repo.myPerformance(mb) }) { d, _ ->
            val t = d.totals
            val roleWord = if (d.asFos) "field agents" else "callers"
            // Top KPIs
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("My cases", t.count.toString(), Modifier.weight(1f), sub = "${t.paid} paid · ${t.unpaid} open")
                Kpi("My book (ENR)", rupee(t.enr), Modifier.weight(1f))
                Kpi("Achieved", "${"%.0f".format(t.achievedPct)}%", Modifier.weight(1f), Good, rupee(t.paidEnr))
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Cash collected", rupee(t.collected), Modifier.weight(1f), Warn, "${rupee(t.pending)} pending")
                Kpi("Total POS", rupee(t.pos), Modifier.weight(1f), sub = "principal outstanding")
                Kpi("Pending", rupee(t.pending), Modifier.weight(1f), Warn)
            }
            TrendStrip(d.trends, "My cash collected — FTD / MTD / LMTD / Overall")
            if (d.portfolios.isEmpty())
                Text("No portfolios assigned to you for this month yet.", color = Muted, modifier = Modifier.padding(8.dp))
            d.portfolios.forEach { MyPortfolioCard(it, roleWord) }
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable
private fun Kpi(label: String, value: String, modifier: Modifier = Modifier, color: Color = TextDark, sub: String? = null) {
    Surface(modifier = modifier, shape = RoundedCornerShape(12.dp), color = CardWhite, contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke)) {
        Column(Modifier.padding(10.dp)) {
            Text(label, color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(value, color = color, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            if (sub != null) Text(sub, color = Muted, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun MyPortfolioCard(p: PerfPortfolio, roleWord: String) {
    Surface(shape = RoundedCornerShape(14.dp), color = CardWhite, contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(p.label, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                p.rank?.let {
                    Surface(shape = RoundedCornerShape(8.dp), color = BrandBlue.copy(alpha = 0.12f)) {
                        Text("🏆 #$it/${p.fieldSize}", color = BrandBlue, fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "Cases ${p.count} · Paid ${p.paid}/${p.count} · ENR ${rupee(p.enr)} · Achieved ${"%.0f".format(p.achievedPct)}%" +
                    (if (p.targetPct > 0) " · Target ${"%.0f".format(p.targetPct)}%" else ""),
                color = Muted, style = MaterialTheme.typography.labelSmall,
            )
            Text(
                "Cash ${rupee(p.collected)} · Pending ${rupee(p.pending)} · POS ${rupee(p.pos)}",
                color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 2.dp),
            )
            Text(
                if (roleWord == "field agents") "🧍 Visited ${p.activity.visited} · 💰 ${p.activity.visitsPaid} with payment"
                else "📞 Contacted ${p.activity.contacted} · ☎️ ${p.activity.calls} calls",
                color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 2.dp),
            )
            if (p.leaderboard.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text("Leaderboard — $roleWord on this portfolio (you are highlighted)",
                    color = Muted, style = MaterialTheme.typography.labelSmall)
                Spacer(Modifier.height(4.dp))
                LeaderHeader()
                p.leaderboard.forEach { LeaderRowView(it) }
            }
        }
    }
}

@Composable
private fun LeaderHeader() {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Cell("#", 0.10f); Cell("Agent", 0.40f); Cell("Cases", 0.16f, end = true)
        Cell("Paid %", 0.16f, end = true); Cell("Cash", 0.18f, end = true)
    }
}

@Composable
private fun LeaderRowView(r: PerfLeaderRow) {
    val bg = if (r.you) BrandBlue.copy(alpha = 0.12f) else Color.Transparent
    Row(Modifier.fillMaxWidth().background(bg, RoundedCornerShape(6.dp)).padding(vertical = 4.dp, horizontal = 2.dp)) {
        Cell(r.rank.toString(), 0.10f, bold = r.you)
        Cell(r.name + if (r.you) " (you)" else "", 0.40f, bold = r.you)
        Cell(r.count.toString(), 0.16f, end = true, bold = r.you)
        Cell("${"%.0f".format(r.achievedPct)}%", 0.16f, end = true, bold = true,
            color = if (r.achievedPct >= 60) Good else if (r.achievedPct >= 30) Warn else TextDark)
        Cell(rupee(r.collected), 0.18f, end = true, color = Good, bold = r.you)
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.Cell(
    text: String, weight: Float, end: Boolean = false, bold: Boolean = false, color: Color = TextDark,
) {
    Text(
        text, color = color,
        fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal,
        style = MaterialTheme.typography.labelSmall,
        textAlign = if (end) androidx.compose.ui.text.style.TextAlign.End else androidx.compose.ui.text.style.TextAlign.Start,
        modifier = Modifier.weight(weight),
    )
}
