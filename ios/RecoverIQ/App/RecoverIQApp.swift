import SwiftUI

/// SwiftUI entry point (replaces the hybrid app's SceneDelegate + WebViewController).
@main
struct RecoverIQApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var app = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            AppRoot()
                .environmentObject(app)
                .preferredColorScheme(.light)
                .tint(.BrandBlue)
        }
        .onChange(of: scenePhase) { phase in
            // Coming back to the app: make sure tracking is running if it should be.
            if phase == .active { LocationTracker.shared.resumeIfEnabled() }
        }
    }
}
