import UIKit
import UserNotifications

/// App entry point.
///
/// iOS can relaunch the app in the BACKGROUND (no screen) after a significant location change, even
/// after the phone restarted or the app was closed. So tracking is resumed here — before any UI —
/// using the session saved in the Keychain, independent of the web page.
@main
final class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        LocationTracker.shared.resumeIfEnabled()
        return true
    }

    func application(_ application: UIApplication,
                     configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let cfg = UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
        cfg.delegateClass = SceneDelegate.self
        return cfg
    }

    /// Swiping the app away stops iOS live location. Remind the field agent to reopen it.
    func applicationWillTerminate(_ application: UIApplication) {
        LocationTracker.shared.notifyPausedIfTracking()
    }

    // Show our local reminders even while the app is open.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .sound])
        } else {
            completionHandler([.alert, .sound])
        }
    }
}

final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let w = UIWindow(windowScene: windowScene)
        w.rootViewController = WebViewController()
        w.makeKeyAndVisible()
        window = w
    }

    func sceneDidBecomeActive(_ scene: UIScene) {
        // Coming back to the app: make sure tracking is running if it should be.
        LocationTracker.shared.resumeIfEnabled()
    }
}
