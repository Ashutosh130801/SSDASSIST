import SwiftUI

/// Pushed destinations on the main NavigationStack.
enum AppRoute: Hashable {
    case caseDetail(Int)
    case ai
}

/// Root router — port of ui/nav/AppRoot.kt (AppRoot + MainNav + HomeScaffold).
///   loading → LogoLoader, logged out → LoginView, dual role just signed in → ViewPickerView,
///   else MainNav (realtime, update check, forced password change, drawer + NavigationStack).
struct AppRoot: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        ZStack(alignment: .bottom) {
            AppTheme.background.ignoresSafeArea()
            content
            if let t = app.toastMessage {
                ToastBanner(text: t)
                    .padding(.bottom, 48)
                    .transition(.opacity)
                    .zIndex(50)
                    .allowsHitTesting(false)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: app.toastMessage)
    }

    @ViewBuilder private var content: some View {
        switch app.state {
        case .loading:
            LogoLoader().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .loggedOut:
            LoginView()
        case .loggedIn(let u):
            if app.pickView && u.availableViews.count > 1 {
                ViewPickerView(user: u)
            } else {
                MainNav(user: u)
                    .id("\(u.id)|\(u.role)|\(u.activeView ?? "")")
            }
        }
    }
}

/// Signed-in shell: realtime channel, handoff/open-case, notifications, broadcast popup, update check,
/// forced password change, NavigationStack with CaseDetailView / AiAssistView destinations.
struct MainNav: View {
    @EnvironmentObject var app: AppState
    let user: User

    @State private var path: [AppRoute] = []
    @State private var broadcast: Realtime.BroadcastMessage? = nil

    var body: some View {
        Group {
            if app.mustChangePassword {
                ForcePasswordChangeView(onChanged: { app.mustChangePassword = false })
            } else {
                NavigationStack(path: $path) {
                    HomeScaffold(user: user,
                                 onOpenCase: { id in path.append(.caseDetail(id)) },
                                 onOpenAi: { path.append(.ai) })
                        .navigationDestination(for: AppRoute.self) { r in destination(r) }
                }
            }
        }
        .onAppear {
            Realtime.shared.connect()
            Notifier.requestPermission()
            Updater.checkAndPrompt()
        }
        .onDisappear { Realtime.shared.disconnect() }
        .onReceive(Realtime.shared.openCase) { id in
            path.append(.caseDetail(id))
        }
        .onReceive(Realtime.shared.notification) { n in
            let nid = n.id > 0 ? n.id : Int(Date().timeIntervalSince1970)
            Notifier.show(id: nid, title: n.title ?? "Update", body: n.body ?? "")
        }
        .onReceive(Realtime.shared.broadcast) { b in
            broadcast = b
            Notifier.show(id: Int(Date().timeIntervalSince1970), title: "📢 " + b.from, body: b.body)
        }
        .alert(item: $broadcast) { b in
            Alert(title: Text("📢 " + b.from), message: Text(b.body), dismissButton: .default(Text("Got it")))
        }
    }

    @ViewBuilder private func destination(_ r: AppRoute) -> some View {
        switch r {
        case .caseDetail(let id): CaseDetailView(caseId: id)
        case .ai: AiAssistView()
        }
    }
}

/// Drawer + top bar + current section, with a section back-stack (Kotlin stackStr / BackHandler),
/// the attendance gate, floating chat + help (guided tour) buttons.
struct HomeScaffold: View {
    @EnvironmentObject var app: AppState
    let user: User
    let onOpenCase: (Int) -> Void
    let onOpenAi: () -> Void

    @SceneStorage("riq.navstack") private var stackStr: String = ""
    @State private var drawerOpen: Bool = false
    @State private var showTour: Bool = false

    private var items: [NavEntry] { NavCatalog.entries(for: user, payslipsOn: app.payslipsOn) }

    private var stack: [String] {
        let valid = Set(items.map { $0.key })
        let s = stackStr.split(separator: "|").map { String($0) }.filter { valid.contains($0) }
        if s.isEmpty { return [items.first?.key ?? "profile"] }
        return s
    }

    private var currentKey: String { stack.last ?? (items.first?.key ?? "profile") }

    private var current: NavEntry {
        items.first(where: { $0.key == currentKey }) ?? items.first ?? NavEntry(key: "profile", label: "My E-ID", icon: "person")
    }

    private func goTo(_ key: String) {
        if key != currentKey { stackStr = (stack + [key]).joined(separator: "|") }
    }

    private func back() {
        let s = stack
        if s.count > 1 { stackStr = s.dropLast().joined(separator: "|") }
    }

    private func closeDrawer() {
        withAnimation(.easeOut(duration: 0.22)) { drawerOpen = false }
    }

    var body: some View {
        ZStack(alignment: .leading) {
            VStack(spacing: 0) {
                topBar
                ZStack(alignment: .bottomTrailing) {
                    NavScreen(key: current.key, onOpenCase: onOpenCase)
                        .id(current.key)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    // Daily check-in gate + presence heartbeat + shift-end prompt (runs app-wide).
                    AttendanceGate()
                    floatingButtons
                }
            }
            if drawerOpen {
                Color.black.opacity(0.35)
                    .ignoresSafeArea()
                    .onTapGesture { closeDrawer() }
                    .transition(.opacity)
                    .zIndex(20)
                drawer
                    .transition(.move(edge: .leading))
                    .zIndex(21)
            }
            if showTour {
                GuidedTour(steps: NavCatalog.tourSteps(user: user, items: items)) {
                    TourPrefs.markSeen(user.role)
                    showTour = false
                }
                .zIndex(30)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .onAppear {
            if !TourPrefs.seen(user.role) { showTour = true }
        }
    }

    // MARK: top bar

    private var topBar: some View {
        HStack(spacing: 4) {
            iconButton("line.3.horizontal", "Menu") {
                withAnimation(.easeOut(duration: 0.22)) { drawerOpen = true }
            }
            if stack.count > 1 {
                iconButton("chevron.left", "Back") { back() }
            }
            Text(current.label)
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(.BrandBlue)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .padding(.leading, 4)
            Spacer(minLength: 4)
            iconButton("clock", "Attendance") { goTo("attendance") }
            iconButton("sparkles", "AI Assist") { onOpenAi() }
        }
        .padding(.horizontal, 6)
        .frame(height: 52)
        .background(Color.TopBar.ignoresSafeArea(edges: .top))
        .overlay(Divider(), alignment: .bottom)
    }

    private func iconButton(_ symbol: String, _ label: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 19, weight: .medium))
                .foregroundColor(.BrandBlue)
                .frame(width: 42, height: 42)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    // MARK: floating buttons

    private var floatingButtons: some View {
        VStack(alignment: .trailing, spacing: 12) {
            // Floating chat — stacked ABOVE the help/tour button.
            ChatButton()
            Button(action: { showTour = true }) {
                Text("?")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.white)
                    .frame(width: 56, height: 56)
                    .background(Circle().fill(Color.BrandBlue))
                    .shadow(color: Color.black.opacity(0.2), radius: 6, x: 0, y: 3)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Help tour")
        }
        .padding(16)
    }

    // MARK: drawer

    private var drawer: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                Text("RecoverIQ").font(.system(size: 22, weight: .bold)).foregroundColor(.BrandBlue)
                Text(user.name + " · " + user.roleLabel).font(.bodySmall).foregroundColor(.Muted).lineLimit(2)
            }
            .padding(16)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(items) { entry in
                        drawerRow(entry.label, entry.icon, selected: entry.key == currentKey) {
                            goTo(entry.key)
                            closeDrawer()
                        }
                    }
                    drawerRow("AI Assist", "sparkles", selected: false) {
                        closeDrawer()
                        onOpenAi()
                    }
                    if user.availableViews.count > 1 {
                        drawerRow("Switch view", "arrow.left.arrow.right", selected: false) {
                            closeDrawer()
                            app.showViewPicker()
                        }
                    }
                    drawerRow("Sign out", "rectangle.portrait.and.arrow.right", selected: false) {
                        closeDrawer()
                        app.logout()
                    }
                    Text("v" + AppInfo.version + " (" + String(AppInfo.build) + ")")
                        .font(.system(size: 10)).foregroundColor(.MutedDim)
                        .padding(.horizontal, 24).padding(.top, 12)
                }
                .padding(.vertical, 8)
            }
        }
        .frame(width: 300)
        .frame(maxHeight: .infinity)
        .background(Color.CardWhite.ignoresSafeArea())
        .shadow(color: Color.black.opacity(0.2), radius: 10, x: 2, y: 0)
        .gesture(
            DragGesture(minimumDistance: 20).onEnded { v in
                if v.translation.width < -60 { closeDrawer() }   // swipe left to close
            }
        )
    }

    private func drawerRow(_ label: String, _ icon: String, selected: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.system(size: 16)).frame(width: 24)
                Text(label).font(.system(size: 15, weight: selected ? .semibold : .regular))
                Spacer()
            }
            .foregroundColor(selected ? .BrandBlue : .TextDark)
            .padding(.horizontal, 16).padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 24).fill(selected ? Color.BrandBlue.opacity(0.12) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 10)
    }
}
