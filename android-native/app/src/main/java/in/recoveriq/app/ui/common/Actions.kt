package `in`.recoveriq.app.ui.common

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File

/** Device actions shared across screens: dial, WhatsApp, and turn-by-turn navigation. */
object Actions {

    private fun cleanPhone(raw: String): String = raw.filter { it.isDigit() || it == '+' }

    /** Normalise to a WhatsApp msisdn (digits only, default +91 for local 10-digit numbers). */
    private fun waNumber(phone: String?): String {
        var p = cleanPhone(phone ?: "")
        p = if (p.startsWith("+")) p.removePrefix("+") else {
            val local = p.trimStart('0')
            if (local.length == 10) "91$local" else local
        }
        return p
    }

    /**
     * Sends a visit summary (optional photo + caption) to a specific WhatsApp number —
     * used so a field agent gets a copy of every visit on their own number.
     */
    fun shareVisitToSelf(context: Context, selfPhone: String?, message: String, photoJpeg: ByteArray?) {
        try {
            val intent = Intent(Intent.ACTION_SEND)
            if (photoJpeg != null) {
                val dir = File(context.cacheDir, "shared").apply { mkdirs() }
                val file = File(dir, "visit_${System.currentTimeMillis()}.jpg")
                file.writeBytes(photoJpeg)
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                intent.type = "image/jpeg"
                intent.putExtra(Intent.EXTRA_STREAM, uri)
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } else {
                intent.type = "text/plain"
            }
            intent.putExtra(Intent.EXTRA_TEXT, message)
            val num = waNumber(selfPhone)
            if (num.isNotBlank()) intent.putExtra("jid", "$num@s.whatsapp.net")
            intent.setPackage("com.whatsapp")
            try {
                context.startActivity(intent)
            } catch (e: Exception) {
                // WhatsApp not installed / self-chat unavailable — fall back to a share sheet.
                val fallback = Intent(intent).apply { setPackage(null) }
                context.startActivity(Intent.createChooser(fallback, "Send visit copy"))
            }
        } catch (e: Exception) {
            toast(context, "Couldn't send the visit copy")
        }
    }

    /**
     * Opens WhatsApp's own contact/group picker with the visit summary + geotagged photo
     * attached, so the field agent can forward it to ANYONE (a colleague, the office, or
     * themselves). No recipient is pre-selected. Falls back to the system share sheet if
     * WhatsApp isn't installed.
     */
    fun shareVisit(context: Context, message: String, photoJpeg: ByteArray?) {
        try {
            val intent = Intent(Intent.ACTION_SEND)
            if (photoJpeg != null) {
                val dir = File(context.cacheDir, "shared").apply { mkdirs() }
                val file = File(dir, "visit_${System.currentTimeMillis()}.jpg")
                file.writeBytes(photoJpeg)
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                intent.type = "image/jpeg"
                intent.putExtra(Intent.EXTRA_STREAM, uri)
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } else {
                intent.type = "text/plain"
            }
            intent.putExtra(Intent.EXTRA_TEXT, message)   // caption for the photo
            // Prefer WhatsApp (personal, then Business); if neither, use the share sheet.
            val pm = context.packageManager
            val wa = when {
                runCatching { pm.getPackageInfo("com.whatsapp", 0) }.isSuccess -> "com.whatsapp"
                runCatching { pm.getPackageInfo("com.whatsapp.w4b", 0) }.isSuccess -> "com.whatsapp.w4b"
                else -> null
            }
            if (wa != null) {
                intent.setPackage(wa)
                context.startActivity(intent)
            } else {
                context.startActivity(Intent.createChooser(Intent(intent).apply { setPackage(null) }, "Share visit"))
            }
        } catch (e: Exception) {
            toast(context, "Couldn't open WhatsApp to share the visit")
        }
    }

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

    /** Open a maps search for a free-text address (used for the customer's new address). */
    fun mapsSearch(context: Context, query: String?) {
        if (query.isNullOrBlank()) { toast(context, "No address"); return }
        val uri = Uri.parse("geo:0,0?q=${Uri.encode(query)}")
        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri)) }
            .onFailure { toast(context, "No maps app available") }
    }

    private fun toast(context: Context, msg: String) =
        Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
}
