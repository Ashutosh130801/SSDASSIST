package `in`.recoveriq.app.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import `in`.recoveriq.app.data.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Restarts location tracking after a reboot or app update — but only for a signed-in
 * field agent, so we never start a service for a logged-out or non-field user.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return

        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val session = Session(context.applicationContext)
                val user = session.user()
                if (user?.isFieldAgent == true && !session.token().isNullOrBlank()) {
                    Log.i("RQTrack", "BootReceiver: restarting tracking for ${user.email}")
                    ContextCompat.startForegroundService(
                        context,
                        android.content.Intent(context, LocationService::class.java)
                            .apply { this.action = LocationService.ACTION_START }
                    )
                }
            } finally {
                pending.finish()
            }
        }
    }
}
