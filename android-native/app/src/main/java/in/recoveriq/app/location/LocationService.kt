package `in`.recoveriq.app.location

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import `in`.recoveriq.app.MainActivity
import `in`.recoveriq.app.R
import `in`.recoveriq.app.data.Api
import `in`.recoveriq.app.data.PingCreate
import `in`.recoveriq.app.data.Repository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Always-on foreground location service.
 *
 * This is the piece that makes tracking survive the app being backgrounded or the phone
 * locked — a native foreground service with foregroundServiceType=location, unlike the
 * old WebView bridge. It posts each fix to /api/tracking/ping over the shared authed
 * OkHttp client (JWT + cert pinning). START_STICKY + BootReceiver keep it alive.
 */
class LocationService : Service() {

    companion object {
        private const val TAG = "RQTrack"
        const val CHANNEL_ID = "recoveriq_location"
        const val NOTIF_ID = 1001

        const val ACTION_START = "in.recoveriq.app.action.START_TRACKING"
        const val ACTION_STOP = "in.recoveriq.app.action.STOP_TRACKING"

        /** Update cadence. Baseline (e.g. standing still) a fix about every 20s — enough to stay
         *  "live" (presence window is 3 min) without writing a LocationPing row every few seconds
         *  per officer, which hammered the DB's single writer. While MOVING the provider may still
         *  deliver as fast as every 3s, so route tracking stays real-time. */
        private const val INTERVAL_MS = 20_000L
        private const val FASTEST_MS = 3_000L
    }

    private lateinit var client: FusedLocationProviderClient
    private lateinit var repo: Repository
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val loc = result.lastLocation ?: run {
                Log.w(TAG, "location result had no location")
                return
            }
            Log.i(TAG, "fix ${loc.latitude},${loc.longitude} acc=${loc.accuracy}")
            postLocation(loc.latitude, loc.longitude, loc.accuracy.toDouble(),
                if (loc.hasSpeed()) loc.speed.toDouble() else null)
        }
    }

    override fun onCreate() {
        super.onCreate()
        client = LocationServices.getFusedLocationProviderClient(this)
        repo = Repository(applicationContext)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            Log.i(TAG, "onStartCommand: STOP")
            stopSelf()
            return START_NOT_STICKY
        }

        Log.i(TAG, "onStartCommand: START")
        startAsForeground()

        // Make sure the shared token cache is hydrated even after a cold process restart.
        scope.launch { repo.bootstrapToken() }
        requestUpdates()
        return START_STICKY
    }

    private fun startAsForeground() {
        val notif = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun requestUpdates() {
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, INTERVAL_MS)
            .setMinUpdateIntervalMillis(FASTEST_MS)
            .setWaitForAccurateLocation(false)
            .build()
        try {
            client.requestLocationUpdates(request, callback, mainLooper)
            Log.i(TAG, "requested location updates OK")
        } catch (e: SecurityException) {
            Log.e(TAG, "NO LOCATION PERMISSION — cannot start updates", e)
            stopSelf()
        }
    }

    private fun postLocation(lat: Double, lng: Double, acc: Double?, speed: Double?) {
        scope.launch {
            try {
                if (Api.token.isNullOrBlank()) repo.bootstrapToken()
                if (Api.token.isNullOrBlank()) {
                    Log.w(TAG, "no token yet — skipping POST")
                    return@launch
                }
                Api.service.ping(PingCreate(latitude = lat, longitude = lng, accuracy = acc, speed = speed))
                Log.i(TAG, "POST ping OK")
            } catch (e: Exception) {
                Log.e(TAG, "POST ping failed: ${e.message}", e)
            }
        }
    }

    private fun buildNotification(): Notification {
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.tracking_notification_title))
            .setContentText(getString(R.string.tracking_notification_text))
            .setSmallIcon(R.drawable.ic_stat_location)
            .setOngoing(true)
            .setContentIntent(open)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.tracking_channel_name),
                NotificationManager.IMPORTANCE_LOW
            )
            ch.setShowBadge(false)
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    override fun onDestroy() {
        Log.i(TAG, "onDestroy — removing updates")
        client.removeLocationUpdates(callback)
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
