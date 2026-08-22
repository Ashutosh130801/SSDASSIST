package `in`.recoveriq.app.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import coil.compose.SubcomposeAsyncImage
import `in`.recoveriq.app.data.FilterOptions
import `in`.recoveriq.app.data.PerfPortfolio
import `in`.recoveriq.app.data.PortfolioBank
import `in`.recoveriq.app.data.ProductSummary
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.theme.Warn

private fun money(v: Double) = "₹" + "%,.0f".format(v)
private fun <T> Set<T>.toggle(v: T): Set<T> = if (contains(v)) minus(v) else plus(v)

/**
 * Bank-first portfolio browsing: banks → products of a bank → (location cards only when a
 * product was uploaded with an explicit branch) → the filtered case list. FOS/caller names on
 * every case are tappable and open that person's performance screen.
 */
@Composable
fun PortfolioScreen(vm: AuthViewModel, onOpenCase: (Int) -> Unit) {
    var bankSel by remember { mutableStateOf<String?>(null) }
    var productSel by remember { mutableStateOf<ProductSummary?>(null) }
    var branchSel by remember { mutableStateOf<String?>(null) }
    var perfTarget by remember { mutableStateOf<Pair<Int, String>?>(null) }
    // Persistent, top-of-section month filter — each month is a separate book (nothing merged).
    var monthB by remember { mutableStateOf("current") }

    val prod = productSel
    val showCases = prod != null && (!prod.branchSplit || branchSel != null)

    perfTarget?.let { (id, role) -> PerformanceDialog(vm, id, role) { perfTarget = null } }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(top = 8.dp)) {
            Text("Month:", color = Muted, style = MaterialTheme.typography.labelSmall)
            listOf("current" to "This month", "next" to "Next", "" to "All").forEach { (v, l) ->
                FilterChip(selected = monthB == v, onClick = { monthB = v }, label = { Text(l) })
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 8.dp)) {
            if (bankSel != null) {
                TextButton(onClick = {
                    when {
                        showCases && prod!!.branchSplit -> branchSel = null      // cases → back to locations
                        productSel != null -> { productSel = null; branchSel = null }  // → back to products
                        else -> bankSel = null                                    // → back to banks
                    }
                }) {
                    Text("← Back", color = BrandBlue)
                }
            }
            SectionTitle(
                when {
                    showCases -> listOfNotNull(prod!!.bank, prod.product, branchSel?.ifBlank { null }).joinToString(" · ")
                    productSel != null -> "${prod!!.bank} · ${prod.product} · locations"
                    bankSel != null -> bankSel!!
                    else -> "Portfolios"
                },
                Modifier.padding(start = 2.dp),
            )
        }

        when {
            showCases -> PortfolioCases(vm, prod!!, branchSel, onOpenCase) { id, role -> perfTarget = id to role }
            productSel != null -> BranchCards(prod!!) { branchSel = it }
            bankSel != null -> ProductCards(vm, bankSel!!, monthB) { p ->
                productSel = p; branchSel = if (p.branchSplit && p.branches.isNotEmpty()) null else ""
            }
            else -> BankCards(vm, monthB) { bankSel = it }
        }
    }
}

@Composable
private fun BankLogo(bank: String, domain: String?, size: Dp = 44.dp) {
    val initials = bank.filter { it.isLetter() }.take(2).uppercase().ifBlank { "#" }
    val box: @Composable () -> Unit = {
        Box(Modifier.size(size).clip(RoundedCornerShape(11.dp)).background(BrandBlue), Alignment.Center) {
            Text(initials, color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
    if (domain.isNullOrBlank()) { box(); return }
    // Clearbit's free logo API was retired; Google's favicon service is reliable + CORS-free.
    SubcomposeAsyncImage(
        model = "https://www.google.com/s2/favicons?sz=128&domain=$domain",
        contentDescription = bank,
        modifier = Modifier.size(size).clip(RoundedCornerShape(11.dp)).background(Color.White),
        contentScale = ContentScale.Fit,
        loading = { box() }, error = { box() },
    )
}

@Composable
private fun MoneyRow(received: Double, pending: Double) {
    Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Column { Text("Recovered", color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(money(received), color = Good, fontWeight = FontWeight.Bold) }
        Column(horizontalAlignment = Alignment.End) { Text("Pending", color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(money(pending), color = Warn, fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun PortfolioCard(content: @Composable () -> Unit, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        shape = RoundedCornerShape(16.dp), color = CardWhite, contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke), shadowElevation = 4.dp,
    ) { Column(Modifier.padding(14.dp)) { content() } }
}

@Composable
private fun BankCards(vm: AuthViewModel, monthB: String, onPick: (String) -> Unit) {
    AsyncContent(key = "banks|$monthB", block = { vm.repo.portfolioBanks(monthB) }) { banks, _ ->
        if (banks.isEmpty()) EmptyState("No cases uploaded yet.")
        else LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp)) {
            items(banks.size) { i ->
                val b: PortfolioBank = banks[i]
                PortfolioCard(content = {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        BankLogo(b.bank, b.logoDomain)
                        Column(Modifier.weight(1f)) {
                            Text(b.bank, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                            Text("${b.productCount} product${if (b.productCount == 1) "" else "s"} · ${b.count} cases",
                                color = Muted, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    MoneyRow(b.received, b.pending)
                }, onClick = { onPick(b.bank) })
            }
        }
    }
}

@Composable
private fun ProductCards(vm: AuthViewModel, bank: String, monthB: String, onPick: (ProductSummary) -> Unit) {
    AsyncContent(key = "prod|$bank|$monthB", block = { vm.repo.productSummary(monthB).filter { it.bank == bank } }) { prods, _ ->
        if (prods.isEmpty()) EmptyState("No products for this bank.")
        else LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp)) {
            items(prods.size) { i ->
                val p = prods[i]
                PortfolioCard(content = {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(p.product, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                        Text("${p.count}", color = Muted)
                    }
                    val sub = listOfNotNull(p.segment, if (p.branchSplit) "📍 ${p.branches.size} locations" else null).joinToString(" · ")
                    if (sub.isNotBlank()) Text(sub, color = Muted, style = MaterialTheme.typography.labelSmall)
                    MoneyRow(p.received, p.pending)
                    if (p.branchSplit) Text("Tap to choose a location →", color = Muted,
                        style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 6.dp))
                }, onClick = { onPick(p) })
            }
        }
    }
}

@Composable
private fun BranchCards(product: ProductSummary, onPick: (String) -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp)) {
        items(product.branches.size) { i ->
            val br = product.branches[i]
            PortfolioCard(content = {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("📍 ${br.branch}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
                    Text("${br.count}", color = Muted)
                }
                Text(product.product, color = Muted, style = MaterialTheme.typography.labelSmall)
                MoneyRow(br.received, br.pending)
            }, onClick = { onPick(br.branch) })
        }
    }
}

@Composable
private fun PortfolioCases(
    vm: AuthViewModel, p: ProductSummary, branch: String?,
    onOpenCase: (Int) -> Unit, onOpenPerf: (Int, String) -> Unit,
) {
    var paid by remember { mutableStateOf<String?>(null) }
    var cycles by remember { mutableStateOf(setOf<String>()) }
    var fos by remember { mutableStateOf(setOf<Int>()) }
    var callers by remember { mutableStateOf(setOf<Int>()) }
    var opts by remember { mutableStateOf(FilterOptions()) }

    LaunchedEffect(p.bank, p.product, branch) {
        opts = try { vm.repo.filterOptions(p.bank, p.product, branch?.ifBlank { null }) } catch (e: Exception) { FilterOptions() }
    }

    Column(Modifier.fillMaxSize()) {
        // ---- filter bar ----
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf<String?>(null, "PAID", "UNPAID", "PARTIAL").forEach { s ->
                FilterChip(selected = paid == s, onClick = { paid = s }, label = { Text(s ?: "All") })
            }
        }
        if (opts.cycles.isNotEmpty()) {
            Spacer(Modifier.height4()); FilterLabel("Cycle")
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                opts.cycles.forEach { c -> FilterChip(selected = cycles.contains(c), onClick = { cycles = cycles.toggle(c) }, label = { Text("Cyc $c") }) }
            }
        }
        if (opts.fos.isNotEmpty()) {
            Spacer(Modifier.height4()); FilterLabel("FOS")
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                opts.fos.forEach { f -> FilterChip(selected = fos.contains(f.id), onClick = { fos = fos.toggle(f.id) },
                    label = { Text(f.name ?: "#${f.id}") }) }
            }
        }
        if (opts.callers.isNotEmpty()) {
            Spacer(Modifier.height4()); FilterLabel("Caller")
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                opts.callers.forEach { f -> FilterChip(selected = callers.contains(f.id), onClick = { callers = callers.toggle(f.id) },
                    label = { Text(f.name ?: "#${f.id}") }) }
            }
        }
        Spacer(Modifier.height(8.dp))

        val key = "${p.bank}|${p.product}|$branch|$paid|${cycles.sorted().joinToString(",")}|${fos.sorted().joinToString(",")}|${callers.sorted().joinToString(",")}"
        AsyncContent(key = key, block = {
            vm.repo.portfolioCases(
                bank = p.bank, product = p.product, branch = branch, paid = paid,
                cycles = cycles.joinToString(","), fosIds = fos.joinToString(","), callerIds = callers.joinToString(","),
            )
        }) { cases, _ ->
            if (cases.isEmpty()) EmptyState("No cases match these filters.")
            else LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 16.dp)) {
                items(cases.size) { i -> CaseCard(cases[i], onClick = { onOpenCase(cases[i].id) }, onOpenPerf = onOpenPerf) }
            }
        }
    }
}

private fun Modifier.height4() = this.then(Modifier.padding(top = 6.dp))

@Composable
private fun FilterLabel(text: String) {
    Text(text, color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp, bottom = 2.dp))
}

@Composable
private fun PerformanceDialog(vm: AuthViewModel, empId: Int, role: String, onDismiss: () -> Unit) {
    var mb by remember { mutableStateOf("current") }
    Dialog(onDismissRequest = onDismiss) {
        Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, contentColor = TextDark) {
            Column(Modifier.padding(16.dp).fillMaxWidth().heightIn(max = 580.dp).verticalScroll(rememberScrollState())) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Performance", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    TextButton(onClick = onDismiss) { Text("Close") }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("current" to "This month", "next" to "Next", "" to "All").forEach { (v, l) ->
                        FilterChip(selected = mb == v, onClick = { mb = v }, label = { Text(l) })
                    }
                }
                Spacer(Modifier.height(8.dp))
                AsyncContent(key = "$empId|$role|$mb", block = { vm.repo.performance(empId, role, mb) }) { d, _ ->
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(listOfNotNull(d.name, d.empCode?.let { "($it)" }, if (d.asFos) "FOS" else "Caller").joinToString(" "),
                            fontWeight = FontWeight.SemiBold)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Metric("Cases", d.totals.count.toString(), Modifier.weight(1f))
                            Metric("Collected", money(d.totals.collected), Modifier.weight(1f), Good)
                            Metric("Achieved", "${"%.0f".format(d.totals.achievedPct)}%", Modifier.weight(1f), BrandBlue)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Metric("Pending", money(d.totals.pending), Modifier.weight(1f), Warn)
                            Metric("Total POS", money(d.totals.pos), Modifier.weight(1f))
                            Spacer(Modifier.weight(1f))
                        }
                        // Activity from the logs they submit.
                        Text(
                            if (d.asFos)
                                "🧍 Visited ${d.activity.visited} cases · 📋 ${d.activity.visits} visits · 💰 ${d.activity.visitsPaid} with payment"
                            else "📞 Contacted ${d.activity.contacted} cases · ☎️ ${d.activity.calls} calls logged",
                            style = MaterialTheme.typography.bodySmall, color = Muted,
                        )
                        TrendStrip(d.trends, "Cash collected — FTD / MTD / LMTD / Overall")
                        d.portfolios.forEach { PerfPortfolioRow(it, d.asFos) }
                        if (d.portfolios.isEmpty()) Text("No cases in this period.", color = Muted)
                    }
                }
            }
        }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier = Modifier, color: Color = TextDark) {
    Surface(modifier = modifier, shape = RoundedCornerShape(10.dp), color = CardWhite, contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke)) {
        Column(Modifier.padding(8.dp)) {
            Text(label, color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(value, color = color, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        }
    }
}

@Composable
private fun PerfPortfolioRow(p: PerfPortfolio, asFos: Boolean) {
    Surface(shape = RoundedCornerShape(12.dp), color = CardWhite, contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(p.label, fontWeight = FontWeight.SemiBold)
                Text("${p.count}", color = Muted)
            }
            Text("Paid ${p.paid}/${p.count} · ENR ${money(p.enr)} · Collected ${money(p.collected)} · ${"%.0f".format(p.achievedPct)}% · POS ${money(p.pos)}" +
                (p.rank?.let { " · Rank #$it/${p.fieldSize}" } ?: ""),
                color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
            Text(
                if (asFos) "🧍 Visited ${p.activity.visited} · 💰 ${p.activity.visitsPaid} with payment"
                else "📞 Contacted ${p.activity.contacted} · ☎️ ${p.activity.calls} calls",
                color = Muted, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 2.dp))
        }
    }
}
