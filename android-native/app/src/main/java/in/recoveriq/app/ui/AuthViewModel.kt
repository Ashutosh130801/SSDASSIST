package `in`.recoveriq.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import `in`.recoveriq.app.data.Repository
import `in`.recoveriq.app.data.User
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
                when {
                    body.contains("2FA_REQUIRED") -> {
                        _needsOtp.value = true
                        _error.value = "Enter your 6-digit authenticator code."
                    }
                    e.code() == 429 -> _error.value = "Too many attempts — try again in a few minutes."
                    e.code() == 403 && body.contains("device", true) ->
                        _error.value = "This device is awaiting admin approval."
                    e.code() == 401 -> _error.value = "Invalid email or password."
                    else -> _error.value = "Sign-in failed (${e.code()})."
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
            repo.logout()
            _needsOtp.value = false
            _state.value = AuthState.LoggedOut
        }
    }
}
