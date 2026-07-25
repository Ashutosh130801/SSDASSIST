package `in`.recoveriq.app.data

import android.util.Log
import `in`.recoveriq.app.BuildConfig
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Listens on the backend WebSocket (/ws) while signed in. When the web app pushes
 * an "open_case" for this user, we emit the case id so the UI can open it on the phone —
 * letting a telecaller work the sheet on the web and call/WhatsApp from mobile.
 */
object Realtime {

    private const val TAG = "RQWS"

    private val _openCase = MutableSharedFlow<Int>(extraBufferCapacity = 8)
    val openCase: SharedFlow<Int> = _openCase

    // Emits a fresh timestamp whenever any data changes on the backend (a log/payment/edit
    // from web or another device) — screens use it to live-refresh, matching the web app.
    private val _dataChanged = MutableSharedFlow<Long>(extraBufferCapacity = 16)
    val dataChanged: SharedFlow<Long> = _dataChanged

    private var socket: WebSocket? = null
    private var wantConnected = false

    private val client = OkHttpClient.Builder()
        .pingInterval(25, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    fun connect() {
        val token = Api.token
        if (token.isNullOrBlank()) return
        wantConnected = true
        openSocket(token)
    }

    fun disconnect() {
        wantConnected = false
        runCatching { socket?.close(1000, "logout") }
        socket = null
    }

    private fun wsUrl(): String {
        // https://host/ -> wss://host/ws ; http://host/ -> ws://host/ws
        val base = BuildConfig.BASE_URL.trimEnd('/')
        val ws = base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        return "$ws/ws"
    }

    private fun openSocket(token: String) {
        val req = Request.Builder()
            .url("${wsUrl()}?token=$token")
            .addHeader("ngrok-skip-browser-warning", "true")
            .build()
        socket = client.newWebSocket(req, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val obj = JSONObject(text)
                    when (obj.optString("type")) {
                        "open_case" -> {
                            val id = obj.optInt("case_id", -1)
                            if (id > 0) _openCase.tryEmit(id)
                        }
                        "data_changed", "case_update" -> _dataChanged.tryEmit(System.currentTimeMillis())
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "bad message: ${e.message}")
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                Log.w(TAG, "ws failure: ${t.message}")
                socket = null
                if (wantConnected) {
                    // Reconnect after a short delay.
                    Thread.sleep(3000)
                    Api.token?.let { if (wantConnected) openSocket(it) }
                }
            }
        })
    }
}
