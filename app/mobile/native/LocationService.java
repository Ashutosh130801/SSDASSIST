package in.recoveriq.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.location.Location;
import android.os.Build;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Foreground location service. Reads GPS via FusedLocationProvider and POSTs each fix to the
 * server (same /api/tracking/ping endpoint the web app uses). Because it's a foreground service
 * with an ongoing notification, Android keeps it running when the app is backgrounded or locked.
 */
public class LocationService extends Service {
    private static final String TAG = "RQTrack";
    private static final String CHANNEL_ID = "recoveriq_tracking";
    private FusedLocationProviderClient client;
    private LocationCallback callback;
    private String pingUrl;
    private String token;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            if (intent.getStringExtra("url") != null) pingUrl = intent.getStringExtra("url");
            if (intent.getStringExtra("token") != null) token = intent.getStringExtra("token");
        }
        Log.i(TAG, "onStartCommand: url=" + pingUrl + " hasToken=" + (token != null && token.length() > 0));
        startForeground(1001, buildNotification());
        startUpdates();
        return START_STICKY;
    }

    private void startUpdates() {
        if (client != null) return;
        client = LocationServices.getFusedLocationProviderClient(this);
        LocationRequest req = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 5000L)
                .setMinUpdateIntervalMillis(3000L)
                .build();
        callback = new LocationCallback() {
            @Override
            public void onLocationResult(LocationResult result) {
                Location loc = result.getLastLocation();
                if (loc != null) {
                    Log.i(TAG, "location " + loc.getLatitude() + "," + loc.getLongitude() + " acc=" + loc.getAccuracy());
                    postLocation(loc);
                } else {
                    Log.w(TAG, "location result had no location");
                }
            }
        };
        try {
            client.requestLocationUpdates(req, callback, Looper.getMainLooper());
            Log.i(TAG, "requested location updates OK");
        } catch (SecurityException e) {
            Log.e(TAG, "NO LOCATION PERMISSION — cannot start updates", e);
        }
    }

    private void postLocation(final Location loc) {
        if (pingUrl == null || pingUrl.length() == 0) return;
        final String url = pingUrl;
        final String tk = token;
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection c = null;
                try {
                    c = (HttpURLConnection) new URL(url).openConnection();
                    c.setConnectTimeout(15000);
                    c.setReadTimeout(15000);
                    c.setRequestMethod("POST");
                    c.setRequestProperty("Content-Type", "application/json");
                    if (tk != null && tk.length() > 0) c.setRequestProperty("Authorization", "Bearer " + tk);
                    c.setDoOutput(true);
                    String body = "{\"latitude\":" + loc.getLatitude()
                            + ",\"longitude\":" + loc.getLongitude()
                            + ",\"accuracy\":" + loc.getAccuracy()
                            + ",\"speed\":" + loc.getSpeed() + "}";
                    OutputStream os = c.getOutputStream();
                    os.write(body.getBytes("UTF-8"));
                    os.flush();
                    os.close();
                    int code = c.getResponseCode();
                    Log.i(TAG, "POST " + url + " -> HTTP " + code);
                } catch (Exception e) {
                    Log.e(TAG, "POST failed to " + url, e);
                } finally {
                    if (c != null) c.disconnect();
                }
            }
        }).start();
    }

    private Notification buildNotification() {
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("RecoverIQ — on duty")
                .setContentText("Sharing your live location with your branch.")
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "Location tracking", NotificationManager.IMPORTANCE_LOW);
            NotificationManager mgr = getSystemService(NotificationManager.class);
            if (mgr != null) mgr.createNotificationChannel(ch);
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (client != null && callback != null) client.removeLocationUpdates(callback);
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
