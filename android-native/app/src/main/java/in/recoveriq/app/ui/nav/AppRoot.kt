package `in`.recoveriq.app.ui.nav

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.SpaceDashboard
import androidx.compose.material.icons.filled.WorkspacePremium
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthState
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.LoginScreen
import `in`.recoveriq.app.ui.admin.AdminDashboardScreen
import `in`.recoveriq.app.ui.admin.LiveMapScreen
import `in`.recoveriq.app.ui.caller.CallQueueScreen
import `in`.recoveriq.app.ui.caller.PtpTrackerScreen
import `in`.recoveriq.app.ui.common.CasesScreen
import `in`.recoveriq.app.ui.common.ProfileScreen
import `in`.recoveriq.app.ui.fos.FieldAgentTrackingScreen
import `in`.recoveriq.app.ui.fos.MyCasesScreen

data class Tab(val key: String, val label: String, val icon: ImageVector, val screen: @Composable () -> Unit)

@Composable
fun AppRoot(
    vm: AuthViewModel,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val state by vm.state.collectAsState()
    when (val s = state) {
        is AuthState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
        is AuthState.LoggedOut -> LoginScreen(vm)
        is AuthState.LoggedIn -> HomeScaffold(
            vm = vm,
            user = s.user,
            onNeedTrackingPermissions = onNeedTrackingPermissions,
            onRequestBatteryExemption = onRequestBatteryExemption,
        )
    }
}

@Composable
private fun HomeScaffold(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val tabs = tabsFor(vm, user, onNeedTrackingPermissions, onRequestBatteryExemption)
    var current by remember { mutableStateOf(0) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEachIndexed { i, tab ->
                    NavigationBarItem(
                        selected = current == i,
                        onClick = { current = i },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        }
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            tabs[current.coerceIn(0, tabs.lastIndex)].screen()
        }
    }
}

private fun tabsFor(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
): List<Tab> {
    val profile = Tab("profile", "Profile", Icons.Filled.Person) { ProfileScreen(vm, user) }
    return when (user.role) {
        "fos" -> listOf(
            Tab("track", "On Duty", Icons.Filled.LocationOn) {
                FieldAgentTrackingScreen(vm, user, onNeedTrackingPermissions, onRequestBatteryExemption)
            },
            Tab("cases", "My Cases", Icons.Filled.Receipt) { MyCasesScreen(vm) },
            profile,
        )
        "telecaller" -> listOf(
            Tab("queue", "Call Queue", Icons.Filled.Phone) { CallQueueScreen(vm) },
            Tab("ptp", "PTP", Icons.Filled.WorkspacePremium) { PtpTrackerScreen(vm) },
            profile,
        )
        else -> listOf( // manager + admin
            Tab("dash", "Dashboard", Icons.Filled.SpaceDashboard) { AdminDashboardScreen(vm, user) },
            Tab("map", "Live Map", Icons.Filled.Map) { LiveMapScreen(vm) },
            Tab("cases", "Cases", Icons.Filled.Groups) { CasesScreen(vm) },
            profile,
        )
    }
}
