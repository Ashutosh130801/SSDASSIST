package `in`.recoveriq.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import `in`.recoveriq.app.ui.AuthState
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.nav.AppRoot
import `in`.recoveriq.app.ui.theme.RecoverIQTheme

class MainActivity : ComponentActivity() {

    // Foreground location + notifications. Background ("Allow all the time") is requested
    // as a second step because Android requires foreground to be granted first.
    private val foregroundPerms = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { result ->
        val granted = result[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            result[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted) requestBackgroundLocation()
    }

    private val backgroundPerm = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* result handled by the OS settings flow when needed */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            RecoverIQTheme {
                val vm: AuthViewModel = viewModel()
                val state by vm.state.collectAsState()
                AppRoot(
                    vm = vm,
                    onNeedTrackingPermissions = { ensureLocationPermissions() },
                    onRequestBatteryExemption = { requestBatteryExemption() },
                )
                // Once a field agent is signed in, make sure permissions are in place.
                if (state is AuthState.LoggedIn && (state as AuthState.LoggedIn).user.isFieldAgent) {
                    // no-op here; the FieldAgent screen calls onNeedTrackingPermissions()
                }
            }
        }
    }

    fun ensureLocationPermissions() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
        if (fine != PackageManager.PERMISSION_GRANTED) {
            val perms = mutableListOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                perms += Manifest.permission.POST_NOTIFICATIONS
            }
            foregroundPerms.launch(perms.toTypedArray())
        } else {
            requestBackgroundLocation()
        }
    }

    private fun requestBackgroundLocation() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val bg = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            if (bg != PackageManager.PERMISSION_GRANTED) {
                backgroundPerm.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            }
        }
    }

    fun requestBatteryExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = getSystemService(android.os.PowerManager::class.java)
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                runCatching {
                    startActivity(
                        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                            .setData(Uri.parse("package:$packageName"))
                    )
                }
            }
        }
    }
}
