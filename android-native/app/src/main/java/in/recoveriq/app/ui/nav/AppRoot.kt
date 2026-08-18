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
import androidx.compose.material.icons.filled.Badge
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
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.sp
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
import `in`.recoveriq.app.ui.common.GuidedTour
import `in`.recoveriq.app.ui.common.TOUR_DESC
import `in`.recoveriq.app.ui.common.TourPrefs
import `in`.recoveriq.app.ui.detail.CaseDetailScreen
import `in`.recoveriq.app.ui.fos.FieldAgentTrackingScreen
import `in`.recoveriq.app.ui.fos.FieldTrackingScreen
import `in`.recoveriq.app.ui.fos.MyCasesScreen
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import `in`.recoveriq.app.ui.screens.ActivityScreen
import `in`.recoveriq.app.ui.screens.CommunicationScreen
import `in`.recoveriq.app.ui.screens.DevicesScreen
import `in`.recoveriq.app.ui.screens.LeaveScreen
import `in`.recoveriq.app.ui.screens.LitigationScreen
import `in`.recoveriq.app.ui.screens.ForcePasswordChangeScreen
import `in`.recoveriq.app.ui.screens.ProfileScreen
import `in`.recoveriq.app.ui.screens.SecurityScreen
import `in`.recoveriq.app.ui.screens.TeamScreen
import `in`.recoveriq.app.ui.teamlead.TeamLeadDashboardScreen
import kotlinx.coroutines.launch

data class NavEntry(val key: String, val label: String, val icon: ImageVector, val screen: @Composable () -> Unit)

@Composable
fun AppRoot(
    vm: AuthViewModel,
    onNeedTrackingPermissions: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
) {
    val state by vm.state.collectAsState()
    val pickView by vm.pickView.collectAsState()
    when (val s = state) {
        is AuthState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
        is AuthState.LoggedOut -> LoginScreen(vm)
        is AuthState.LoggedIn ->
            if (pickView && s.user.availableViews.size > 1) ViewPickerScreen(vm, s.user)
            else MainNav(vm, s.user, onNeedTrackingPermissions, onRequestBatteryExemption)
    }
}

private fun viewMeta(v: String): Triple<String, String, String> = when (v) {
    "teamlead" -> Triple("👥", "Team Leader", "Your team’s cases, MIS & DPR")
    "fos" -> Triple("🗺️", "Field Agent", "Your field visits & route")
    "telecaller" -> Triple("📞", "Tele-calling", "Your calling queue")
    "manager" -> Triple("🏢", "Manager", "Branch overview")
    "headoffice" -> Triple("🏛️", "Head Office", "All portfolios")
    "admin" -> Triple("🛡️", "Administrator", "Full access")
    else -> Triple("•", v, "")
}

/** Dual-role "which hat?" picker, shown after login and on Switch view. One hat at a time. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ViewPickerScreen(vm: AuthViewModel, user: User) {
    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(12.dp),
    ) {
        androidx.compose.foundation.layout.Spacer(Modifier.padding(top = 24.dp))
        Text("Choose your view", style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold, color = BrandBlue)
        Text("Hi ${user.name.substringBefore(' ')} — you have more than one role. Pick how to work now; you can switch anytime.",
            style = MaterialTheme.typography.bodyMedium, color = Muted)
        user.availableViews.forEach { v ->
            val (ic, title, sub) = viewMeta(v)
            androidx.compose.material3.Card(
                onClick = { vm.switchView(v) },
                colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = CardWhite),
                modifier = Modifier.fillMaxSize(),
            ) {
                androidx.compose.foundation.layout.Row(
                    Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(14.dp),
                ) {
                    Text(ic, style = MaterialTheme.typography.headlineMedium)
                    Column(Modifier.weight(1f)) {
                        Text(title + (if (v == user.activeView) "  ·  current" else ""),
                            fontWeight = FontWeight.Bold, color = TextDark)
                        Text(sub, style = MaterialTheme.typography.bodySmall, color = Muted)
                    }
                    Text("→", color = Muted)
                }
            }
        }
        androidx.compose.material3.TextButton(onClick = { vm.logout() }) { Text("Sign out") }
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
    // Targeted alerts (e.g. caller/head-office updated a customer's new address/phone) →
    // post a phone notification so the field officer sees it even outside the app.
    val appCtx = androidx.compose.ui.platform.LocalContext.current.applicationContext
    LaunchedEffect(Unit) {
        Realtime.notification.collect { n ->
            `in`.recoveriq.app.Notifier.show(
                appCtx, n.id.takeIf { it > 0 } ?: System.currentTimeMillis().toInt(),
                n.title ?: "Update", n.body ?: "",
            )
        }
    }

    // Field officers are signed out at 7pm each day (checked while the app is open).
    if (user.isFieldAgent) {
        LaunchedEffect(Unit) {
            while (true) {
                val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
                if (hour >= 19) { vm.logout(); break }
                kotlinx.coroutines.delay(60_000)
            }
        }
    }

    // Offer an in-app update if a newer build is published to the server.
    `in`.recoveriq.app.UpdateGate()

    // First login with the shared starter password: force a change before anything else.
    var mustChange by remember { mutableStateOf(user.mustChangePassword) }
    if (mustChange) {
        ForcePasswordChangeScreen(vm, onChanged = { mustChange = false })
        return
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

    // One-time guided tour (per role) + a "?" button to reopen it anytime.
    val ctx = LocalContext.current
    var showTour by remember { mutableStateOf(!TourPrefs.seen(ctx, user.role)) }
    val tourSteps = remember(items) {
        buildList {
            add("👋 Welcome, ${user.name.substringBefore(' ')}!" to
                "A quick tour of your ${user.roleLabel} workspace — we'll walk through each feature. Skip anytime and reopen it from the \"?\" button at the bottom-right.")
            items.forEach { add(it.label to (TOUR_DESC[it.key] ?: "Open ${it.label}.")) }
            add("🎉 You're all set!" to "That's the tour. Tap the \"?\" button anytime to see it again. Happy working!")
        }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet(
                drawerContainerColor = CardWhite,
                drawerContentColor = TextDark,
            ) {
                val itemColors = NavigationDrawerItemDefaults.colors(
                    selectedContainerColor = BrandBlue.copy(alpha = 0.12f),
                    selectedIconColor = BrandBlue,
                    selectedTextColor = BrandBlue,
                    // Transparent pill on the white sheet + strong dark text/icons so every
                    // item is clearly legible (was rendering dark-on-dark).
                    unselectedContainerColor = androidx.compose.ui.graphics.Color.Transparent,
                    unselectedIconColor = TextDark,
                    unselectedTextColor = TextDark,
                )
                Column(Modifier.padding(16.dp)) {
                    Text("RecoverIQ", style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold, color = BrandBlue)
                    Text(user.name + " · " + user.roleLabel, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                    items.forEach { entry ->
                        NavigationDrawerItem(
                            label = { Text(entry.label) },
                            icon = { Icon(entry.icon, null) },
                            selected = entry.key == currentKey,
                            colors = itemColors,
                            onClick = { currentKey = entry.key; scope.launch { drawerState.close() } },
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                        )
                    }
                    NavigationDrawerItem(
                        label = { Text("AI Assist") },
                        icon = { Icon(Icons.Filled.AutoAwesome, null) },
                        selected = false,
                        colors = itemColors,
                        onClick = { scope.launch { drawerState.close() }; onOpenAi() },
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                    )
                    if (user.availableViews.size > 1) {
                        NavigationDrawerItem(
                            label = { Text("Switch view") },
                            icon = { Icon(Icons.Filled.SwapHoriz, null) },
                            selected = false,
                            colors = itemColors,
                            onClick = { scope.launch { drawerState.close() }; vm.showViewPicker() },
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp),
                        )
                    }
                    NavigationDrawerItem(
                        label = { Text("Sign out") },
                        icon = { Icon(Icons.AutoMirrored.Filled.Logout, null) },
                        selected = false,
                        colors = itemColors,
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
                        containerColor = androidx.compose.ui.graphics.Color(0xF2FFFFFF),
                        titleContentColor = MaterialTheme.colorScheme.primary,
                        navigationIconContentColor = MaterialTheme.colorScheme.primary,
                        actionIconContentColor = MaterialTheme.colorScheme.primary,
                    ),
                )
            },
            containerColor = androidx.compose.ui.graphics.Color.Transparent,
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                current.screen()
                // Floating help / tour button (bottom-right).
                FloatingActionButton(
                    onClick = { showTour = true },
                    containerColor = BrandBlue,
                    contentColor = Color.White,
                    modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                ) { Text("?", fontWeight = FontWeight.Bold, fontSize = 22.sp) }

                if (showTour) {
                    GuidedTour(tourSteps) { TourPrefs.markSeen(ctx, user.role); showTour = false }
                }
            }
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
    val profile = NavEntry("profile", "My E-ID", Icons.Filled.Badge) { ProfileScreen(vm, user) }
    val leave = NavEntry("leave", "Leave", Icons.Filled.BeachAccess) { LeaveScreen(vm, user) }
    val security = NavEntry("security", "Security", Icons.Filled.Lock) { SecurityScreen(vm, user) }

    return when (user.role) {
        "fos" -> listOf(
            // Home dashboard leads with the On Duty on/off switch.
            NavEntry("dashboard", "My Stats", Icons.Filled.SpaceDashboard) {
                DashboardScreen(vm, user, onNeedTrackingPermissions, onRequestBatteryExemption)
            },
            NavEntry("onduty", "On Duty", Icons.Filled.LocationOn) {
                FieldAgentTrackingScreen(vm, user, onNeedTrackingPermissions, onRequestBatteryExemption)
            },
            NavEntry("fcases", "My Accounts", Icons.Filled.Receipt) { MyCasesScreen(vm, onOpenCase) },
            NavEntry("fmap", "Field Tracking", Icons.Filled.Map) { FieldTrackingScreen(vm) },
            profile, leave, security,
        )
        "telecaller" -> listOf(
            dashboard,
            NavEntry("queue", "Calling", Icons.Filled.Phone) { CallQueueScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            profile, leave, security,
        )
        "teamlead" -> listOf(
            NavEntry("tldash", "My Team", Icons.Filled.Groups) { TeamLeadDashboardScreen(vm, onOpenCase) },
            NavEntry("cases", "Team Accounts", Icons.Filled.Receipt) { CasesScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            profile, leave, security,
        )
        "manager" -> listOf(
            dashboard,
            NavEntry("cases", "Accounts", Icons.Filled.Receipt) { CasesScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            NavEntry("legal", "Litigation", Icons.Filled.Gavel) { LitigationScreen(vm) },
            NavEntry("map", "Field Tracking", Icons.Filled.Map) { LiveMapScreen(vm) },
            NavEntry("staff", "Team", Icons.Filled.Groups) { TeamScreen(vm) },
            profile, leave,
            NavEntry("templates", "Communication", Icons.Filled.Phone) { CommunicationScreen(vm) },
            NavEntry("devices", "Devices", Icons.Filled.PhoneAndroid) { DevicesScreen(vm) },
            security,
        )
        // HR / IT / office staff: identity card + leave + security (no case portfolios).
        "hr", "it", "staff" -> listOf(profile, leave, security)
        else -> listOf( // admin + head office
            dashboard,
            NavEntry("cases", "Accounts", Icons.Filled.Receipt) { CasesScreen(vm, onOpenCase) },
            NavEntry("ptp", "PTP Tracker", Icons.Filled.Handshake) { PtpTrackerScreen(vm, onOpenCase) },
            NavEntry("legal", "Litigation", Icons.Filled.Gavel) { LitigationScreen(vm) },
            NavEntry("map", "Field Tracking", Icons.Filled.Map) { LiveMapScreen(vm) },
            NavEntry("records", "Activity", Icons.Filled.History) { ActivityScreen(vm) },
            NavEntry("staff", "Team", Icons.Filled.Groups) { TeamScreen(vm) },
            profile, leave,
            NavEntry("templates", "Communication", Icons.Filled.Phone) { CommunicationScreen(vm) },
            NavEntry("devices", "Devices", Icons.Filled.PhoneAndroid) { DevicesScreen(vm) },
            security,
        )
    }
}
