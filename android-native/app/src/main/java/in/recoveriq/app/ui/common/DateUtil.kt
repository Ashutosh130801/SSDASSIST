package `in`.recoveriq.app.ui.common

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Date helpers that work on all supported API levels (no java.time / desugaring needed). */
object DateUtil {

    private val iso = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    private val isoUtc = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }

    /** ISO date (UTC) from the epoch millis a Material DatePicker returns. */
    fun isoFromMillis(millis: Long): String = isoUtc.format(Date(millis))

    /** Epoch millis (UTC midnight) for an ISO date, to seed a DatePicker. */
    fun millisFromIso(isoDate: String?): Long? =
        if (isoDate.isNullOrBlank()) null
        else runCatching { isoUtc.parse(isoDate.take(10))?.time }.getOrNull()

    /** Inclusive day count between two ISO dates (start & end counted). */
    fun daysInclusive(startIso: String, endIso: String): Int {
        val a = millisFromIso(startIso) ?: return 1
        val b = millisFromIso(endIso) ?: return 1
        val d = ((b - a) / 86_400_000L).toInt() + 1
        return if (d < 1) 1 else d
    }
    // Timestamps are shown in IST; dates (calendar days) are shown as-is (no zone shift).
    private val IST = TimeZone.getTimeZone("Asia/Kolkata")
    private val pretty = SimpleDateFormat("dd MMM, hh:mm a", Locale.US).apply { timeZone = IST }
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
            // Server timestamps are UTC (naive on SQLite) — parse as UTC, print in IST.
            val src = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }
            pretty.format(src.parse(isoTs.take(19))!!)
        }.getOrDefault(isoTs.take(16).replace('T', ' '))
    }

    fun humanDate(isoTs: String?): String {
        if (isoTs.isNullOrBlank()) return ""
        return runCatching { prettyDate.format(iso.parse(isoTs.take(10))!!) }
            .getOrDefault(isoTs.take(10))
    }
}
