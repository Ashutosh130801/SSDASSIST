package `in`.recoveriq.app.data

import android.util.Log
import com.squareup.moshi.Moshi
import `in`.recoveriq.app.BuildConfig
import okhttp3.CertificatePinner
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Single source of truth for the network stack:
 *  - HTTPS base URL from BuildConfig (no cleartext allowed by the manifest).
 *  - Certificate pinning via OkHttp CertificatePinner (BuildConfig.CERT_PIN).
 *  - JWT bearer token attached to every request from an in-memory cache that
 *    the Session hydrates on launch and login, so the background service is authed too.
 */
object Api {

    private const val TAG = "RQNet"

    /** Cached bearer token, updated by Session on login/launch. Read synchronously by the interceptor. */
    @Volatile
    var token: String? = null

    val moshi: Moshi = Moshi.Builder().build()
    val moshiUser = moshi.adapter(User::class.java)

    private val host: String
        get() = BuildConfig.BASE_URL.toHttpUrlOrNull()?.host ?: "localhost"

    private val authInterceptor = Interceptor { chain ->
        val b = chain.request().newBuilder()
        // Skip ngrok's free-tier browser-warning interstitial so API calls get real JSON.
        b.header("ngrok-skip-browser-warning", "true")
        // A stable User-Agent so a Cloudflare WAF/allow rule can identify (and whitelist) the app.
        b.header("User-Agent", "RecoverIQ-Android/${BuildConfig.VERSION_NAME}")
        val hadToken = !token.isNullOrBlank()
        token?.takeIf { it.isNotBlank() }?.let { b.header("Authorization", "Bearer $it") }
        val resp = chain.proceed(b.build())
        // Token rejected (e.g. FOS 7pm expiry) — signal the app to drop to login.
        if (resp.code == 401 && hadToken) AuthEvents.forceLogout.tryEmit(Unit)
        resp
    }

    private val client: OkHttpClient by lazy {
        val b = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(45, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            // Force HTTP/1.1. Cloudflare Tunnel frequently resets HTTP/2 streams mid-response,
            // which surfaces in the app as a bogus "Network error" even though the request
            // already reached the origin. HTTP/1.1 is far more reliable through the tunnel.
            .protocols(listOf(okhttp3.Protocol.HTTP_1_1))
            .addInterceptor(authInterceptor)

        // Certificate pinning — only when a pin is supplied at build time.
        val pin = BuildConfig.CERT_PIN
        if (pin.isNotBlank()) {
            val pinner = CertificatePinner.Builder()
                .add(host, pin)
                .build()
            b.certificatePinner(pinner)
            Log.i(TAG, "Certificate pinning enabled for $host")
        } else {
            Log.w(TAG, "CERT_PIN empty — pinning disabled (TLS still enforced).")
        }

        if (BuildConfig.DEBUG) {
            b.addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            })
        }
        b.build()
    }

    val service: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(ApiService::class.java)
    }
}
