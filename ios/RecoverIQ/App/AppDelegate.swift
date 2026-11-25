import UIKit
import UserNotifications

/// UIKit app delegate (hooked into the SwiftUI lifecycle via @UIApplicationDelegateAdaptor).
///
/// iOS can relaunch the app in the BACKGROUND (no UI) after a significant location change, even after
/// the phone restarted or the app was closed. So tracking is resumed here — before any UI — using the
/// session saved in the Keychain.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        LocationTracker.shared.resumeIfEnabled()
        return true
    }

    /// Swiping the app away stops iOS live location. Remind the field agent to reopen it.
    func applicationWillTerminate(_ application: UIApplication) {
        LocationTracker.shared.notifyPausedIfTracking()
    }

    // Show our local notifications even while the app is open.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

/// Local notifications (port of Notifier.kt).
enum Notifier {
    static func show(id: Int, title: String, body: String) {
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = body
        c.sound = .default
        let req = UNNotificationRequest(identifier: "riq.n.\(id)", content: c, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }

    static func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }
}
