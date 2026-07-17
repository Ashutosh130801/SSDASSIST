package `in`.recoveriq.app.location

import android.content.Context
import android.content.Intent
import android.os.Build

/** Start/stop helpers for the background location service. */
object Tracking {

    fun start(context: Context) {
        val i = Intent(context, LocationService::class.java).apply { action = LocationService.ACTION_START }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(i)
        } else {
            context.startService(i)
        }
    }

    fun stop(context: Context) {
        val i = Intent(context, LocationService::class.java).apply { action = LocationService.ACTION_STOP }
        context.startService(i)
    }
}
