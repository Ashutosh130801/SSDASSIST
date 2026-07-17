package `in`.recoveriq.app.ui.common

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast

/** Device actions shared across screens: dial, WhatsApp, and turn-by-turn navigation. */
object Actions {

    private fun cleanPhone(raw: String): String = raw.filter { it.isDigit() || it == '+' }

    fun dial(context: Context, phone: String?) {
        val p = phone?.let { cleanPhone(it) }.orEmpty()
        if (p.isBlank()) { toast(context, "No phone number on file"); return }
        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$p")))
    }

    fun whatsapp(context: Context, phone: String?, message: String? = null) {
        var p = phone?.let { cleanPhone(it) }.orEmpty()
        if (p.isBlank()) { toast(context, "No phone number on file"); return }
        // wa.me needs a country code; default to India (+91) for local 10-digit numbers.
        if (!p.startsWith("+")) {
            p = p.trimStart('0')
            if (p.length == 10) p = "91$p"
        } else {
            p = p.removePrefix("+")
        }
        val url = buildString {
            append("https://wa.me/").append(p)
            if (!message.isNullOrBlank()) append("?text=").append(Uri.encode(message))
        }
        runCatching {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        }.onFailure { toast(context, "WhatsApp not available") }
    }

    /** Open turn-by-turn navigation to a coordinate (Google Maps if present, else any maps app). */
    fun navigate(context: Context, lat: Double?, lng: Double?, label: String? = null) {
        if (lat == null || lng == null) { toast(context, "No location saved for this case"); return }
        val nav = Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=$lat,$lng")).apply {
            setPackage("com.google.android.apps.maps")
        }
        if (nav.resolveActivity(context.packageManager) != null) {
            context.startActivity(nav); return
        }
        val geo = Uri.parse("geo:$lat,$lng?q=$lat,$lng(${Uri.encode(label ?: "Destination")})")
        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, geo)) }
            .onFailure { toast(context, "No maps app available") }
    }

    private fun toast(context: Context, msg: String) =
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
}
