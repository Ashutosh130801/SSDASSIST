package `in`.recoveriq.app.ui.common

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.R
import `in`.recoveriq.app.data.Realtime
import `in`.recoveriq.app.data.Trends
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Good
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark

/**
 * A key that changes whenever the backend broadcasts a data change over the WebSocket.
 * Pass it as AsyncContent(key = rememberLiveKey()) to auto-refresh a screen live, exactly
 * like the web app's useDataChanged hook.
 */
/**
 * Branded loading indicator — the SSD coin gently coin-flips and pulses. Replaces the plain
 * spinner wherever the app is loading content.
 */
@Composable
fun LogoLoader(modifier: Modifier = Modifier, size: Dp = 60.dp) {
    val tr = rememberInfiniteTransition(label = "ssd-loader")
    val flip by tr.animateFloat(
        0f, 360f, infiniteRepeatable(tween(1200, easing = LinearEasing)), label = "flip",
    )
    val pulse by tr.animateFloat(
        0.9f, 1.03f,
        infiniteRepeatable(tween(700, easing = LinearEasing), RepeatMode.Reverse), label = "pulse",
    )
    Image(
        painter = painterResource(R.drawable.ssd_logo),
        contentDescription = "Loading",
        modifier = modifier.size(size).graphicsLayer {
            rotationY = flip; scaleX = pulse; scaleY = pulse; cameraDistance = 16f * density
        },
    )
}

@Composable
fun rememberLiveKey(): Long {
    val v by Realtime.dataChanged.collectAsState(initial = 0L)
    return v
}

sealed interface Load<out T> {
    data object Loading : Load<Nothing>
    data class Ok<T>(val data: T) : Load<T>
    data class Err(val message: String) : Load<Nothing>
}

/**
 * Loads [block] once (and on [key] change) and renders one of loading / error / content.
 * Keeps screens terse without a ViewModel per list.
 */
@Composable
fun <T> AsyncContent(
    key: Any? = Unit,
    modifier: Modifier = Modifier,
    block: suspend () -> T,
    content: @Composable (T, reload: () -> Unit) -> Unit,
) {
    var state by remember(key) { mutableStateOf<Load<T>>(Load.Loading) }
    var nonce by remember(key) { mutableStateOf(0) }

    LaunchedEffect(key, nonce) {
        state = Load.Loading
        state = try {
            Load.Ok(block())
        } catch (e: Exception) {
            Load.Err(e.message ?: "Something went wrong")
        }
    }

    val reload: () -> Unit = { nonce += 1 }
    when (val s = state) {
        is Load.Loading -> Box(modifier.fillMaxSize(), Alignment.Center) { LogoLoader() }
        is Load.Err -> Box(modifier.fillMaxSize(), Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(s.message, color = MaterialTheme.colorScheme.error)
                Button(onClick = reload) { Text("Retry") }
            }
        }
        is Load.Ok -> content(s.data, reload)
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier.padding(vertical = 8.dp),
    )
}

/**
 * Cash-collected comparison across time windows: FTD (today) / MTD (month-till-day) /
 * LMTD (last month-till-day) / Overall. Shown on the FOS/caller dashboard + profile, and on
 * the report card a team lead / manager opens.
 */
@Composable
fun TrendStrip(trends: Trends, title: String? = null, modifier: Modifier = Modifier) {
    fun money(v: Double) = "₹" + "%,.0f".format(v)
    val cells = listOf(
        Triple("FTD", "Today", trends.ftd),
        Triple("MTD", "This month", trends.mtd),
        Triple("LMTD", "Last month", trends.lmtd),
        Triple("Overall", "Lifetime", trends.overall),
    )
    Column(modifier.fillMaxWidth()) {
        if (title != null) {
            Text(title, color = Muted, style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(bottom = 6.dp))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            cells.forEach { (lbl, hint, v) ->
                Surface(
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(10.dp),
                    color = CardWhite,
                    contentColor = TextDark,
                    border = BorderStroke(1.dp, GlassStroke),
                ) {
                    Column(Modifier.padding(8.dp)) {
                        Text(lbl, color = Muted, style = MaterialTheme.typography.labelSmall)
                        Text(hint, color = Muted, style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Normal)
                        Text(money(v), style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                            color = if (lbl == "FTD") Good else TextDark)
                    }
                }
            }
        }
    }
}

@Composable
fun InfoCard(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = CardWhite,
        contentColor = TextDark,
        border = BorderStroke(1.dp, GlassStroke),
        shadowElevation = 6.dp,
    ) {
        Column(Modifier.padding(16.dp)) { content() }
    }
}

@Composable
fun <T> DataList(
    items: List<T>,
    emptyText: String,
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(16.dp),
    row: @Composable (T) -> Unit,
) {
    if (items.isEmpty()) {
        Box(modifier.fillMaxSize(), Alignment.Center) {
            Text(emptyText, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = contentPadding,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(items.size) { i -> row(items[i]) }
    }
}
