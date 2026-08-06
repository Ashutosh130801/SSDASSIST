package `in`.recoveriq.app.ui

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import `in`.recoveriq.app.data.AuthEvents
import `in`.recoveriq.app.data.Repository
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.location.Tracking
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException

sealed interface AuthState {
    data object Loading : AuthState
    data object LoggedOut : AuthState
    data class LoggedIn(val user: User) : AuthState
}

class AuthViewModel(app: Application) : AndroidViewModel(app) {

    val repo = Repository(app)

    private val _state = MutableStateFlow<AuthState>(AuthState.Loading)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    /** True when the server said "2FA_REQUIRED" — the UI should show the OTP field. */
    private val _needsOtp = MutableStateFlow(false)
    val needsOtp: StateFlow<Boolean> = _needsOtp.asStateFlow()

    /** True right after a dual-role user logs in (or taps Switch view): show the hat picker.
     *  NOT set on session restore, so it doesn't nag on every app launch. */
    private val _pickView = MutableStateFlow(false)
    val pickView: StateFlow<Boolean> = _pickView.asStateFlow()
    fun showViewPicker() { _pickView.value = true }

    init {
        viewModelScope.launch {
            repo.bootstrapToken()
            val user = repo.currentUser()
            _state.value = if (user != null && repo.isLoggedIn()) AuthState.LoggedIn(user) else AuthState.LoggedOut
        }
        // Server rejected the token (e.g. field officer's 7pm expiry) → drop to login.
        viewModelScope.launch {
            AuthEvents.forceLogout.collect {
                if (_state.value is AuthState.LoggedIn) logout()
            }
        }
    }

    fun login(email: String, password: String, otp: String?) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val token = repo.login(email, password, otp)
                _needsOtp.value = false
                _pickView.value = token.user.availableViews.size > 1   // dual role → ask which hat
                _state.value = AuthState.LoggedIn(token.user)
            } catch (e: HttpException) {
                val body = runCatching { e.response()?.errorBody()?.string() }.getOrNull().orEmpty()
                // Pull the human-readable reason the server sent, e.g. {"detail":"..."}
                val detail = Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"")
                    .find(body)?.groupValues?.getOrNull(1)
                when {
                    body.contains("2FA_REQUIRED") -> {
                        _needsOtp.value = true
                        _error.value = "Enter your 6-digit authenticator code."
                    }
                    e.code() == 429 -> _error.value = "Too many attempts — try again in a few minutes."
                    e.code() == 403 ->
                        _error.value = detail ?: "This device is awaiting admin approval."
                    e.code() == 401 -> _error.value = "Invalid email or password."
                    e.code() >= 500 ->
                        _error.value = "Server error — the backend is down or out of disk space. Contact your admin."
                    else -> _error.value = detail ?: "Sign-in failed (${e.code()})."
                }
            } catch (e: javax.net.ssl.SSLPeerUnverifiedException) {
                // Cert-pin mismatch (common when the server is behind Cloudflare, which rotates
                // certificates). The app needs rebuilding with an EMPTY CERT_PIN.
                _error.value = "Secure-connection check failed (certificate pin). The app must be rebuilt without pinning."
            } catch (e: javax.net.ssl.SSLException) {
                _error.value = "TLS/SSL error reaching the server. If it uses Cloudflare, rebuild the app without cert pinning."
            } catch (e: java.net.UnknownHostException) {
                _error.value = "Can't find the server — check the app's server address / your DNS."
            } catch (e: java.net.SocketTimeoutException) {
                _error.value = "Server received the request but didn't reply in time. Please try again."
            } catch (e: java.net.ConnectException) {
                _error.value = "Can't connect to the server (it may be down)."
            } catch (e: Exception) {
                // Surface the exception class so the exact cause is visible in the field.
                _error.value = "Network error (${e.javaClass.simpleName}). Check your connection."
            } finally {
                _busy.value = false
            }
        }
    }

    /** Dual-role: switch the active hat (caller/FOS ↔ team lead) and re-render as that view. */
    fun switchView(view: String) {
        viewModelScope.launch {
            runCatching { repo.switchView(view) }
                .onSuccess { _pickView.value = false; _state.value = AuthState.LoggedIn(it.user) }
                .onFailure { _error.value = "Could not switch view." }
        }
    }

    fun logout() {
        viewModelScope.launch {
            runCatching { Tracking.stop(getApplication<Application>() as Context) }   // stop background location if on duty
            repo.logout()
            _needsOtp.value = false
            _state.value = AuthState.LoggedOut
        }
    }
}
