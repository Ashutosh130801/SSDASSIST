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

    // Dual-role: flip the active "view" (e.g. caller ↔ team lead). Returns a fresh token.
    @POST("api/auth/switch-view")
    suspend fun switchView(@Body body: Map<String, String>): Token

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
        @Query("product") product: String? = null,
        @Query("branch") branch: String? = null,
        @Query("status") status: String? = null,
        @Query("paid_status") paidStatus: String? = null,
        @Query("search") search: String? = null,
        @Query("cycles") cycles: String? = null,
        @Query("fos_ids") fosIds: String? = null,
        @Query("caller_ids") callerIds: String? = null,
        @Query("limit") limit: Int = 500,
    ): List<Case>

    // Bank-first portfolio navigation + filter dropdown options.
    @GET("api/cases/portfolio-banks")
    suspend fun portfolioBanks(@Query("month_bucket") monthBucket: String? = null): List<PortfolioBank>

    @GET("api/cases/product-summary")
    suspend fun productSummary(@Query("month_bucket") monthBucket: String? = null): List<ProductSummary>

    @GET("api/cases/filter-options")
    suspend fun filterOptions(
        @Query("bank") bank: String? = null,
        @Query("product") product: String? = null,
        @Query("branch") branch: String? = null,
    ): FilterOptions

    // Any FOS/caller's performance (clickable name → performance screen).
    @GET("api/mis/performance")
    suspend fun performance(
        @Query("emp_id") empId: Int,
        @Query("role") role: String? = null,
        @Query("month_bucket") monthBucket: String = "current",
    ): Performance

    // The signed-in caller's/FOS's OWN scorecard + per-portfolio leaderboard.
    @GET("api/mis/my-performance")
    suspend fun myPerformance(
        @Query("month_bucket") monthBucket: String = "current",
        @Query("bank") bank: String? = null,
        @Query("product") product: String? = null,
    ): Performance

    @GET("api/cases/{id}")
    suspend fun case(@Path("id") id: Int): Case

    // Personal colour highlight (review later) — empty color clears it.
    @POST("api/cases/{id}/review-flag")
    suspend fun setReviewFlag(@Path("id") id: Int, @Body body: Map<String, String?>): Case

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

    @GET("api/reminders")
    suspend fun reminders(): RemindersResponse

    @GET("api/calls/ptp-tracker")
    suspend fun ptpTracker(
        @Query("bank") bank: String? = null,
        @Query("date_from") dateFrom: String? = null,
        @Query("date_to") dateTo: String? = null,
    ): PtpResponse

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
        @Part("norm_stab") normStab: RequestBody?,
        @Part("disposition") disposition: RequestBody?,
        @Part("ptp_date") ptpDate: RequestBody?,
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

    // FTD/MTD/LMTD/Overall achievement for one person (self, or a report for a manager/TL).
    @GET("api/mis/employee-trends")
    suspend fun employeeTrends(@Query("user_id") userId: Int): EmployeeTrends

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

    // --- Team lead ---
    @GET("api/team/overview")
    suspend fun teamOverview(): TeamOverview

    @GET("api/team/my-team")
    suspend fun myTeam(): List<TeamMemberCard>

    // --- Team / users ---
    @GET("api/users")
    suspend fun users(@Query("role") role: String? = null): List<User>

    @POST("api/users")
    suspend fun createUser(@Body body: UserCreate): User

    @PATCH("api/users/{id}")
    suspend fun updateUser(@Path("id") id: Int, @Body body: UserUpdate): User

    @DELETE("api/users/{id}")
    suspend fun deleteUser(@Path("id") id: Int)

    // --- Leave ---
    @GET("api/leaves")
    suspend fun leaves(@Query("status") status: String? = null, @Query("scope") scope: String = "auto",
                       @Query("leave_type") leaveType: String? = null,
                       @Query("from_date") fromDate: String? = null,
                       @Query("to_date") toDate: String? = null,
                       @Query("q") q: String? = null): List<Leave>

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

    // --- My E-ID / profile ---
    @GET("api/manpower/me")
    suspend fun myProfile(): EmployeeProfile

    @PATCH("api/manpower/me")
    suspend fun updateMyProfile(@Body body: Map<String, String?>): Map<String, Any?>

    @Multipart
    @POST("api/manpower/me/photo")
    suspend fun uploadProfilePhoto(@Part file: MultipartBody.Part): Map<String, Any?>

    @POST("api/auth/change-password")
    suspend fun changePassword(@Body body: ChangePasswordRequest): Token

    // --- Profile change requests ---
    @GET("api/manpower/me/change-fields")
    suspend fun myChangeFields(): List<ChangeField>

    @POST("api/manpower/me/change-request")
    suspend fun submitChangeRequest(@Body body: Map<String, String?>): ProfileChangeRequest

    @GET("api/manpower/me/change-requests")
    suspend fun myChangeRequests(): List<ProfileChangeRequest>

    @GET("api/manpower/change-requests")
    suspend fun changeRequests(@Query("status") status: String? = null,
                               @Query("q") q: String? = null): List<ProfileChangeRequest>

    @POST("api/manpower/change-requests/{id}/{decision}")
    suspend fun decideChangeRequest(@Path("id") id: Int, @Path("decision") decision: String,
                                    @Body body: Map<String, String?>): ProfileChangeRequest

    // --- Notifications (bell) ---
    @GET("api/notifications")
    suspend fun notifications(@Query("limit") limit: Int = 30): NotificationList

    @POST("api/notifications/{id}/read")
    suspend fun markNotificationRead(@Path("id") id: Int)

    @POST("api/notifications/read-all")
    suspend fun markAllNotificationsRead()

    // --- Customer contact update (caller / head office) ---
    @PATCH("api/cases/{id}/contact-update")
    suspend fun contactUpdate(@Path("id") id: Int, @Body body: Map<String, String?>): Case
}
