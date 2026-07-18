package `in`.recoveriq.app.ui.nav

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.BeachAccess
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.Handshake
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.SpaceDashboard
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import `in`.recoveriq.app.data.Realtime
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthState
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.LoginScreen
import `in`.recoveriq.app.ui.admin.DashboardScreen
import `in`.recoveriq.app.ui.admin.LiveMapScreen
import `in`.recoveriq.app.ui.ai.AiAssistScreen
import `in`.recoveriq.app.ui.caller.CallQueueScreen
import `in`.recoveriq.app.ui.caller.PtpTrackerScreen
import `in`.recoveriq.app.ui.common.CasesScreen
import `in`.recoveriq.app.ui.detail.CaseDetailScreen
import `in`.recoveriq.app.ui.fos.FieldAgentTrackingScreen
import `in`.recoveriq.app.ui.fos.FieldTrackingScreen
import `in`.recoveriq.app.ui.fos.MyCasesScreen
import `in`.recoveriq.app.ui.screens.ActivityScreen
import `in`.recoveriq.app.ui.screens.CommunicationScreen
import `in`.recoveriq.app.ui.screens.DevicesScreen
import `in`.recoveriq.app.ui.screens.LeaveScreen
import `in`.recoveriq.app.ui.screens.LitigationScreen
import `in`.recoveriq.app.ui.screens.SecurityScreen
import `in`.recoveriq.app.ui.screens.TeamScreen
import kotlinx.coroutines.launch

data class NavEntry(val key: String, val label: String, val icon: ImageVector, val screen: @Composable () -> Unit)

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
        is AuthState.LoggedIn -> MainNav(vm, s.user, onNeedTrackingPermissions, onRequestBatteryExemption)
    }
}

@Composable
private fun MainNav(
    vm: AuthViewModel,
    user: User,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val nav = rememberNavController()

    // Live channel: connect while signed in; open a case the web pushed to this phone.
    DisposableEffect(Unit) {
        Realtime.connect()
        onDispose { Realtime.disconnect() }
    }
    LaunchedEffect(Unit) {
        Realtime.openCase.collect { id -> nav.navigate("case/$id") }
    }

    NavHost(navController = nav, startDestination = "home") {
        composable("home") {
            HomeScaffold(
                vm = vm, user = user,
                onOpenCase = { nav.navigate("case/$it") },
                onOpenAi = { nav.navigate("ai") },
                onNeedTrackingPermissions = onNeedTrackingPermissions,
                onRequestBatteryExemption = onRequestBatteryExemption,
            )
        }
        composable(
            "case/{id}",
            arguments = listOf(navArgument("id") { type = NavType.IntType }),
        ) { backStack ->
            val id = backStack.arguments?.getInt("id") ?: return@composable
            CaseDetailScreen(vm, user, id, onBack = { nav.popBackStack() })
        }
        composable("ai") { AiAssistScreen(vm, user, onBack = { nav.popBackStack() }) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HomeScaffold(
    vm: AuthViewModel,
    user: User,
    onOpenCase: (Int) -> Unit,
    onOpenAi: () -> Unit,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val items = remember(user.role) {
        navEntriesFor(vm, user, onOpenCase, onNeedTrackingPermissions, onRequestBatteryExemption)
    }
    var currentKey by remember { mutableStateOf(items.first().key) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val current = items.firstOrNull { it.key == currentKey } ?: items.first()

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.padding(16.dp)) {
                    Text("RecoverIQ", style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                    Text(user.name + " · " + user.roleLabel, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    items.forEach { entry ->
                        NavigationDrawerItem(
                            label = { Text(entry.label) },
                            icon = { Icon(entry.icon, null) },
                            selected = entry.key == currentKey,
                            onClick = { currentKey = entry.key; scope.launch { drawerState.close() } },
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                        )
                    }
                    NavigationDrawerItem(
                        label = { Text("AI Assist") },
                        icon = { Icon(Icons.Filled.AutoAwesome, null) },
                        selected = false,
                        onClick = { scope.launch { drawerState.close() }; onOpenAi() },
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                    )
                    NavigationDrawerItem(
                        label = { Text("Sign out") },
                        icon = { Icon(Icons.AutoMirrored.Filled.Logout, null) },
                        selected = false,
                        onClick = { scope.launch { drawerState.close() }; vm.logout() },
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                    )
                }
            }
        },
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(current.label) },
                    navigationIcon = {
                        androidx.compose.material3.IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Filled.Menu, "Menu")
                        }
                    },
                    actions = {
                        androidx.compose.material3.IconButton(onClick = onOpenAi) {
                            Icon(Icons.Filled.AutoAwesome, "AI Assist")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                        titleContentColor = MaterialTheme.colorScheme.primary,
                        navigationIconContentColor = MaterialTheme.colorScheme.primary,
                        actionIconContentColor = MaterialTheme.colorScheme.primary,
                    ),
                )
            },
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) { current.screen() }
        }
    }
}

private fun navEntriesFor(
    vm: AuthViewModel,
    user: User,
    onOpenCase: (Int) -> Unit,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
): List<NavEntry> {
    val dashboard = NavEntry("dashboard", if (user.isFieldAgent || user.isTelecaller) "My Stats" else "Dashboard",
        Icons.Filled.SpaceDashboard) { DashboardScreen(vm, user) }
    val leave = NavEntry("leave", "Leave", Icons.Filled.BeachAccess) { LeaveScreen(vm, user) }
    val security = NavEntry("security", "Security", Icons.Filled.Lock) { SecurityScreen(vm, user) }

    return when (user.role) {
        "fos" -> listOf(
            dashboard,
            NavEntry("onduty", "On Duty", Icons.Filled.LocationOn) {
                FieldAgentTrackingScreen(vm, user, onNeedTrackingPermissions, onRequestBatteryExemption)
            },
            NavEntry("fcases", "My Accounts", Icons.Filled.Receipt) { MyCasesScreen(vm, onOpenCase) },
            NavEntry("fmap", "Field Tracking", Icons.Filled.Map) { FieldTrackingScreen(vm) },
            leave, security,
        )
        "telecaller" -> listOf(
            dashboard,
            NavEntry("queue", "Calling", Icons.Filled.Phone) { CallQueueScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            leave, security,
        )
        "manager" -> listOf(
            dashboard,
            NavEntry("cases", "Accounts", Icons.Filled.Receipt) { CasesScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            NavEntry("legal", "Litigation", Icons.Filled.Gavel) { LitigationScreen(vm) },
            NavEntry("map", "Field Tracking", Icons.Filled.Map) { LiveMapScreen(vm) },
            NavEntry("staff", "Team", Icons.Filled.Groups) { TeamScreen(vm) },
            leave,
            NavEntry("templates", "Communication", Icons.Filled.Phone) { CommunicationScreen(vm) },
            NavEntry("devices", "Devices", Icons.Filled.PhoneAndroid) { DevicesScreen(vm) },
            security,
        )
        else -> listOf( // admin
            dashboard,
            NavEntry("cases", "Accounts", Icons.Filled.Receipt) { CasesScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            NavEntry("legal", "Litigation", Icons.Filled.Gavel) { LitigationScreen(vm) },
            NavEntry("map", "Field Tracking", Icons.Filled.Map) { LiveMapScreen(vm) },
            NavEntry("records", "Activity", Icons.Filled.History) { ActivityScreen(vm) },
            NavEntry("staff", "Team", Icons.Filled.Groups) { TeamScreen(vm) },
            leave,
            NavEntry("templates", "Communication", Icons.Filled.Phone) { CommunicationScreen(vm) },
            NavEntry("devices", "Devices", Icons.Filled.PhoneAndroid) { DevicesScreen(vm) },
            security,
        )
    }
}
