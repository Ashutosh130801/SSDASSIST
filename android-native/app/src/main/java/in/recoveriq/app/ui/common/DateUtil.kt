package `in`.recoveriq.app.ui.common

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/** Date helpers that work on all supported API levels (no java.time / desugaring needed). */
object DateUtil {

    private val iso = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    private val pretty = SimpleDateFormat("dd MMM, HH:mm", Locale.US)
    private val prettyDate = SimpleDateFormat("dd MMM yyyy", Locale.US)

    /** ISO date [days] from today, e.g. plusDaysIso(1) = tomorrow. */
    fun plusDaysIso(days: Int): String {
        val c = Calendar.getInstance()
        c.add(Calendar.DAY_OF_YEAR, days)
        return iso.format(c.time)
    }

    /** Best-effort pretty-print of a backend ISO timestamp; falls back to the raw string. */
    fun humanTime(isoTs: String?): String {
        if (isoTs.isNullOrBlank()) return ""
        return runCatching {
            val src = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
            pretty.format(src.parse(isoTs.take(19))!!)
        }.getOrDefault(isoTs.take(16).replace('T', ' '))
    }

    fun humanDate(isoTs: String?): String {
        if (isoTs.isNullOrBlank()) return ""
        return runCatching { prettyDate.format(iso.parse(isoTs.take(10))!!) }
            .getOrDefault(isoTs.take(10))
    }
}
