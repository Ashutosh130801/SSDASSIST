package `in`.recoveriq.app.data

import kotlinx.coroutines.flow.MutableSharedFlow

/**
 * Global "you've been logged out" signal. Emitted when the server rejects the token
 * (HTTP 401) — e.g. a field officer's token expiring at 7pm IST — so the UI can drop
 * to the login screen automatically.
 */
object AuthEvents {
    val forceLogout = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
}
