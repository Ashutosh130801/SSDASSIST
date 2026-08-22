package `in`.recoveriq.app.ui.common

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark

/** Remembers, per role + tour version, whether the one-time guided tour has been shown.
 *  Bump TOUR_VERSION whenever the app changes enough that everyone should see it again. */
const val TOUR_VERSION = 1

object TourPrefs {
    private const val FILE = "ssd_tour"
    private fun key(role: String) = "seen_${role}_v$TOUR_VERSION"
    fun seen(ctx: Context, role: String): Boolean =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).getBoolean(key(role), false)
    fun markSeen(ctx: Context, role: String) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putBoolean(key(role), true).apply()
    }
}

/** Plain-language description for each nav destination (mirrors the web tour). */
val TOUR_DESC: Map<String, String> = mapOf(
    "dashboard" to "Your home base — headline numbers at a glance: cases, recovery %, cash collected, pending and your resolution %.",
    "onduty" to "On Duty — turn tracking on when you start the day so your live location is shared with the office.",
    "tldash" to "My Team — your team's overview, members and their performance, all scoped to you.",
    "cases" to "Accounts — browse your portfolios and open any case for full details, payments and history.",
    "fcases" to "My Accounts — your assigned field cases grouped by bank & bucket. Search, filter, or open a case.",
    "queue" to "Calling — your call queue: due now, contacted today, upcoming and paid. Search & filter to work faster.",
    "ptp" to "PTP Tracker — promise-to-pay cases split into overdue / due today / upcoming so you chase the right ones first.",
    "map" to "Field Tracking — live agent locations, routes and visit history.",
    "fmap" to "Field Tracking — your live location and today's route; log GPS-stamped visits from a case.",
    "records" to "Activity — a live log of every call, visit and payment.",
    "staff" to "Team — staff profiles and performance.",
    "templates" to "Communication — WhatsApp / SMS message templates.",
    "devices" to "Devices — approve or block the devices your staff log in from.",
    "legal" to "Litigation — the legal / court case tracker.",
    "leave" to "Leave — apply for leave and track approvals.",
    "security" to "Security — change your password and set up 2-factor authentication.",
    "profile" to "My E-ID — your profile, ID card, personal details and your achievement trends.",
    "myperf" to "My Performance — your scorecard per portfolio: achievement %, cash, POS, and the portfolio leaderboard with your rank against peers.",
)

/**
 * A one-time, skippable onboarding carousel. Steps are (title, body) pairs. Dimmed scrim behind
 * a centered card with Back / Next / Skip and progress dots — the familiar app-tour pattern.
 */
@Composable
fun GuidedTour(steps: List<Pair<String, String>>, onClose: () -> Unit) {
    if (steps.isEmpty()) return
    var idx by remember { mutableIntStateOf(0) }
    val last = idx == steps.lastIndex
    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0xCC0B1733))
            // consume taps on the scrim so the screen behind doesn't react
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) {},
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = CardWhite,
            contentColor = TextDark,
            shadowElevation = 12.dp,
            modifier = Modifier.padding(24.dp).widthIn(max = 400.dp),
        ) {
            Column(Modifier.padding(20.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(steps[idx].first, style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    TextButton(onClick = onClose) { Text("Skip") }
                }
                Spacer(Modifier.height(6.dp))
                Text(steps[idx].second, style = MaterialTheme.typography.bodyMedium, color = Muted)
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        steps.indices.forEach { i ->
                            Box(Modifier.size(7.dp).clip(CircleShape)
                                .background(if (i == idx) BrandBlue else Color(0xFFD1D5DB)))
                        }
                    }
                    if (idx > 0) TextButton(onClick = { idx-- }) { Text("Back") }
                    Button(onClick = { if (last) onClose() else idx++ }) { Text(if (last) "Done" else "Next") }
                }
                Text("Step ${idx + 1} of ${steps.size}", style = MaterialTheme.typography.labelSmall,
                    color = Muted, modifier = Modifier.padding(top = 6.dp))
            }
        }
    }
}
