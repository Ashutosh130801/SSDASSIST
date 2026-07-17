package in.recoveriq.app;

import android.Manifest;
import android.content.Intent;
import android.os.Build;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

/**
 * Bridges the web app to the native LocationService, and requests the runtime location /
 * notification permissions it needs.
 * JS: Capacitor.registerPlugin('Tracker').start({ url, token })  /  .stop()
 */
@CapacitorPlugin(
    name = "Tracker",
    permissions = {
        @Permission(alias = "location", strings = {
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        }),
        @Permission(alias = "notifications", strings = {
            Manifest.permission.POST_NOTIFICATIONS
        })
    }
)
public class TrackerPlugin extends Plugin {

    @PluginMethod
    public void start(PluginCall call) {
        // Ask for location (and, on Android 13+, notification) permission, then start the service.
        requestAllPermissions(call, "afterPermission");
    }

    @PermissionCallback
    private void afterPermission(PluginCall call) {
        Intent i = new Intent(getContext(), LocationService.class);
        i.putExtra("url", call.getString("url"));
        i.putExtra("token", call.getString("token"));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getContext().startForegroundService(i);
        } else {
            getContext().startService(i);
        }
        call.resolve();
    }

    @PluginMethod
    public void stop(PluginCall call) {
        getContext().stopService(new Intent(getContext(), LocationService.class));
        call.resolve();
    }
}
