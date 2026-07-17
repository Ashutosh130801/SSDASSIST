package `in`.recoveriq.app.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Retrofit interface mapping the RecoverIQ FastAPI endpoints. */
interface ApiService {

    @POST("api/auth/login-json")
    suspend fun login(@Body body: LoginRequest): Token

    @GET("api/auth/me")
    suspend fun me(): User

    // --- Tracking ---
    @POST("api/tracking/ping")
    suspend fun ping(@Body body: PingCreate): PingOut

    @GET("api/tracking/live")
    suspend fun liveOfficers(): List<OfficerLocation>

    @GET("api/tracking/me/today")
    suspend fun myTodayRoute(): List<PingOut>

    @GET("api/tracking/officer/{id}/route")
    suspend fun officerRoute(
        @Path("id") officerId: Int,
        @Query("date") date: String? = null,
    ): List<PingOut>

    // --- Cases ---
    @GET("api/cases")
    suspend fun cases(
        @Query("assigned_to_me") mine: Boolean? = null,
        @Query("status") status: String? = null,
        @Query("bank") bank: String? = null,
    ): List<Case>

    @GET("api/cases/{id}")
    suspend fun case(@Path("id") id: Int): Case

    @PATCH("api/cases/{id}")
    suspend fun updateCase(@Path("id") id: Int, @Body body: CaseUpdate): Case

    @POST("api/cases/{id}/payment")
    suspend fun recordPayment(@Path("id") id: Int, @Body body: PaymentRequest): Case

    // --- Calls (telecaller) ---
    @GET("api/calls/queue")
    suspend fun callQueue(@Query("segment") segment: String? = null): List<Case>

    @GET("api/calls/ptp-tracker")
    suspend fun ptpTracker(): List<Case>
}
