package `in`.recoveriq.app.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "recoveriq_session")

/**
 * Persists the JWT + the signed-in user across app restarts and process death,
 * so the background location service can authenticate even if the UI isn't open.
 */
class Session(private val context: Context) {

    private val KEY_TOKEN = stringPreferencesKey("jwt")
    private val KEY_USER = stringPreferencesKey("user_json")
    private val KEY_DEVICE = stringPreferencesKey("device_id")
    private val KEY_ONDUTY = booleanPreferencesKey("on_duty")

    /** Persisted "on duty" flag so the tracking toggle survives tab switches / process death. */
    val onDutyFlow: Flow<Boolean> = context.dataStore.data.map { it[KEY_ONDUTY] ?: false }
    suspend fun setOnDuty(v: Boolean) { context.dataStore.edit { it[KEY_ONDUTY] = v } }
    suspend fun onDuty(): Boolean = context.dataStore.data.first()[KEY_ONDUTY] ?: false

    val tokenFlow: Flow<String?> = context.dataStore.data.map { it[KEY_TOKEN] }
    val userFlow: Flow<User?> = context.dataStore.data.map { prefs ->
        prefs[KEY_USER]?.let { runCatching { Api.moshiUser.fromJson(it) }.getOrNull() }
    }

    suspend fun token(): String? = context.dataStore.data.first()[KEY_TOKEN]

    suspend fun user(): User? = context.dataStore.data.first()[KEY_USER]
        ?.let { runCatching { Api.moshiUser.fromJson(it) }.getOrNull() }

    suspend fun save(token: Token) {
        context.dataStore.edit {
            it[KEY_TOKEN] = token.accessToken
            it[KEY_USER] = Api.moshiUser.toJson(token.user)
        }
    }

    suspend fun clear() {
        context.dataStore.edit {
            it.remove(KEY_TOKEN)
            it.remove(KEY_USER)
            it[KEY_ONDUTY] = false
        }
    }

    /** A stable per-install device id used for the login device-gate. */
    suspend fun deviceId(): String {
        val existing = context.dataStore.data.first()[KEY_DEVICE]
        if (existing != null) return existing
        val fresh = "android-" + java.util.UUID.randomUUID().toString().take(12)
        context.dataStore.edit { it[KEY_DEVICE] = fresh }
        return fresh
    }
}
