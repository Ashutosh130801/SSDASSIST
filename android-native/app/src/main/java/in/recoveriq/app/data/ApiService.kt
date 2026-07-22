package `in`.recoveriq.app.data

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
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
    suspend fun myTodayRoute(): TodayRoute

    @GET("api/tracking/officer/{id}/route")
    suspend fun officerRoute(
        @Path("id") officerId: Int,
        @Query("date") date: String? = null,
    ): List<PingOut>

    // --- Cases ---
    @GET("api/cases")
    suspend fun cases(
        @Query("bank") bank: String? = null,
        @Query("status") status: String? = null,
        @Query("paid_status") paidStatus: String? = null,
        @Query("search") search: String? = null,
        @Query("limit") limit: Int = 500,
    ): List<Case>

    @GET("api/cases/{id}")
    suspend fun case(@Path("id") id: Int): Case

    @PATCH("api/cases/{id}")
    suspend fun updateCase(@Path("id") id: Int, @Body body: CaseUpdate): Case

    @POST("api/cases/{id}/payment")
    suspend fun recordPayment(@Path("id") id: Int, @Body body: PaymentRequest): Case

    @GET("api/cases/{id}/timeline")
    suspend fun timeline(@Path("id") id: Int): List<TimelineEvent>

    // --- Calls (telecaller) ---
    @POST("api/calls")
    suspend fun logCall(@Body body: CallCreate): CallOut

    @GET("api/calls/queue")
    suspend fun callQueue(@Query("bank") bank: String? = null): QueueResponse

    @GET("api/calls/ptp-tracker")
    suspend fun ptpTracker(@Query("bank") bank: String? = null): PtpResponse

    @GET("api/calls/case/{id}")
    suspend fun callsForCase(@Path("id") id: Int): List<CallOut>

    // --- Visits (field) ---
    @GET("api/visits/case/{id}")
    suspend fun visitsForCase(@Path("id") id: Int): List<VisitOut>

    @Multipart
    @POST("api/visits")
    suspend fun createVisit(
        @Part("case_id") caseId: RequestBody,
        @Part("latitude") latitude: RequestBody?,
        @Part("longitude") longitude: RequestBody?,
        @Part("gps_accuracy") gpsAccuracy: RequestBody?,
        @Part("person_moved") personMoved: RequestBody,
        @Part("paid") paid: RequestBody,
        @Part("amount_collected") amountCollected: RequestBody,
        @Part("disposition") disposition: RequestBody?,
        @Part("note") note: RequestBody?,
        @Part photo: MultipartBody.Part?,
    ): VisitOut

    // --- Templates / messaging ---
    @GET("api/templates")
    suspend fun templates(): List<Template>

    @POST("api/templates")
    suspend fun createTemplate(@Body body: TemplateCreate): Template

    @DELETE("api/templates/{id}")
    suspend fun deleteTemplate(@Path("id") id: Int)

    @POST("api/templates/log")
    suspend fun logComm(@Body body: CommLog)

    // --- Dashboard / activity ---
    @GET("api/analytics/dashboard")
    suspend fun dashboard(): DashboardResponse

    @GET("api/analytics/activity")
    suspend fun activity(@Query("kind") kind: String = "all", @Query("limit") limit: Int = 100): List<ActivityItem>

    // --- Litigation ---
    @GET("api/legal")
    suspend fun legalCases(): List<Legal>

    @POST("api/legal")
    suspend fun createLegal(@Body body: LegalCreate): Legal

    @DELETE("api/legal/{id}")
    suspend fun deleteLegal(@Path("id") id: Int)

    @GET("api/legal/insights")
    suspend fun legalInsights(): LegalInsights

    // --- Team / users ---
    @GET("api/users")
    suspend fun users(): List<User>

    @POST("api/users")
    suspend fun createUser(@Body body: UserCreate): User

    @PATCH("api/users/{id}")
    suspend fun updateUser(@Path("id") id: Int, @Body body: UserUpdate): User

    @DELETE("api/users/{id}")
    suspend fun deleteUser(@Path("id") id: Int)

    // --- Leave ---
    @GET("api/leaves")
    suspend fun leaves(@Query("status") status: String? = null, @Query("scope") scope: String = "auto"): List<Leave>

    @POST("api/leaves")
    suspend fun applyLeave(@Body body: LeaveCreate): Leave

    @GET("api/leaves/balance")
    suspend fun leaveBalance(): List<LeaveBalance>

    @POST("api/leaves/{id}/{decision}")
    suspend fun decideLeave(@Path("id") id: Int, @Path("decision") decision: String): Leave

    // --- Devices ---
    @GET("api/devices")
    suspend fun devices(): List<Device>

    @POST("api/devices/{id}/approve")
    suspend fun approveDevice(@Path("id") id: Int)

    @POST("api/devices/{id}/revoke")
    suspend fun revokeDevice(@Path("id") id: Int)

    @DELETE("api/devices/{id}")
    suspend fun deleteDevice(@Path("id") id: Int)

    // --- 2FA (security) ---
    @GET("api/auth/2fa/status")
    suspend fun twoFAStatus(): TwoFAStatus

    @POST("api/auth/2fa/setup")
    suspend fun twoFASetup(): TwoFASetup

    @POST("api/auth/2fa/enable")
    suspend fun twoFAEnable(@Body body: OtpBody): TwoFAStatus

    @POST("api/auth/2fa/disable")
    suspend fun twoFADisable(@Body body: OtpBody): TwoFAStatus

    // --- AI Assist ---
    @POST("api/ai")
    suspend fun aiAssist(@Body body: AIRequest): AIResponse
}
