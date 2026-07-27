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
            } catch (e: Exception) {
                _error.value = "Network error — check your connection."
            } finally {
                _busy.value = false
            }
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
