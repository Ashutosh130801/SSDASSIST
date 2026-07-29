package `in`.recoveriq.app.data

import android.content.Context
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Thin repository over ApiService. Keeps the in-memory token cache (Api.token)
 * in lockstep with the persisted Session so both UI and the background service authenticate.
 */
class Repository(context: Context) {

    private val session = Session(context.applicationContext)

    suspend fun bootstrapToken() {
        Api.token = session.token()
    }

    // On-duty flag (persisted) so the tracking toggle reflects real state everywhere.
    val onDutyFlow get() = session.onDutyFlow
    suspend fun setOnDuty(v: Boolean) = session.setOnDuty(v)
    suspend fun onDuty(): Boolean = session.onDuty()

    suspend fun currentUser(): User? = session.user()

    suspend fun isLoggedIn(): Boolean = !session.token().isNullOrBlank()

    suspend fun login(email: String, password: String, otp: String?): Token {
        val deviceId = session.deviceId()
        val token = Api.service.login(
            LoginRequest(
                email = email.trim().lowercase(),
                password = password,
                otp = otp?.ifBlank { null },
                deviceId = deviceId,
                deviceLabel = android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL,
            )
        )
        Api.token = token.accessToken
        session.save(token)
        return token
    }

    suspend fun logout() {
        Api.token = null
        session.clear()
    }

    private suspend fun myId(): Int? = session.user()?.id

    /** Cases assigned to the signed-in user (fos or caller), filtered client-side. */
    suspend fun myCases(): List<Case> {
        val id = myId()
        return Api.service.cases(limit = 1000).filter { it.assignedFosId == id || it.assignedCallerId == id }
    }

    suspend fun allCases(
        bank: String? = null, status: String? = null, search: String? = null,
    ): List<Case> = Api.service.cases(bank = bank, status = status, search = search?.ifBlank { null })

    suspend fun case(id: Int): Case = Api.service.case(id)
    suspend fun updateCase(id: Int, update: CaseUpdate): Case = Api.service.updateCase(id, update)
    suspend fun recordPayment(id: Int, amount: Double, mode: String = "UPI", note: String? = null, normStab: String? = null): Case =
        Api.service.recordPayment(id, PaymentRequest(amount, mode, note, normStab))
    suspend fun timeline(id: Int): List<TimelineEvent> = Api.service.timeline(id)
    suspend fun callsForCase(id: Int): List<CallOut> = Api.service.callsForCase(id)
    suspend fun visitsForCase(id: Int): List<VisitOut> = Api.service.visitsForCase(id)

    suspend fun logCall(body: CallCreate): CallOut = Api.service.logCall(body)

    suspend fun liveOfficers(): List<OfficerLocation> = Api.service.liveOfficers()
    suspend fun myTodayRoute(): TodayRoute = Api.service.myTodayRoute()
    suspend fun officerRoute(id: Int, date: String? = null): List<PingOut> =
        Api.service.officerRoute(id, date)

    suspend fun callQueue(bank: String? = null): QueueResponse = Api.service.callQueue(bank)
    suspend fun ptpTracker(bank: String? = null): PtpResponse = Api.service.ptpTracker(bank)
    suspend fun reminders(): RemindersResponse = Api.service.reminders()

    suspend fun templates(): List<Template> = Api.service.templates()
    suspend fun logComm(caseId: Int, channel: String, text: String?) =
        Api.service.logComm(CommLog(caseId, channel, text))

    suspend fun aiAssist(prompt: String, context: String? = null): String =
        Api.service.aiAssist(AIRequest(prompt, context)).reply

    // --- Dashboard / activity ---
    suspend fun dashboard(): DashboardResponse = Api.service.dashboard()
    suspend fun activity(kind: String = "all"): List<ActivityItem> = Api.service.activity(kind)

    // --- Litigation ---
    suspend fun legalCases(): List<Legal> = Api.service.legalCases()
    suspend fun legalInsights(): LegalInsights = Api.service.legalInsights()
    suspend fun createLegal(body: LegalCreate): Legal = Api.service.createLegal(body)
    suspend fun deleteLegal(id: Int) = Api.service.deleteLegal(id)

    // --- Team ---
    suspend fun users(): List<User> = Api.service.users()
    suspend fun usersByRole(role: String): List<User> = Api.service.users(role)
    suspend fun teamOverview(): TeamOverview = Api.service.teamOverview()
    suspend fun myTeam(): List<TeamMemberCard> = Api.service.myTeam()
    suspend fun createUser(body: UserCreate): User = Api.service.createUser(body)
    suspend fun updateUser(id: Int, body: UserUpdate): User = Api.service.updateUser(id, body)
    suspend fun deleteUser(id: Int) = Api.service.deleteUser(id)

    // --- Leave ---
    suspend fun leaves(status: String? = null, scope: String = "auto"): List<Leave> =
        Api.service.leaves(status, scope)
    suspend fun applyLeave(body: LeaveCreate): Leave = Api.service.applyLeave(body)
    suspend fun leaveBalance(): List<LeaveBalance> = Api.service.leaveBalance()
    suspend fun decideLeave(id: Int, approve: Boolean): Leave =
        Api.service.decideLeave(id, if (approve) "approve" else "reject")

    // --- Devices ---
    suspend fun devices(): List<Device> = Api.service.devices()
    suspend fun approveDevice(id: Int) = Api.service.approveDevice(id)
    suspend fun revokeDevice(id: Int) = Api.service.revokeDevice(id)
    suspend fun deleteDevice(id: Int) = Api.service.deleteDevice(id)

    // --- Templates ---
    suspend fun createTemplate(body: TemplateCreate): Template = Api.service.createTemplate(body)
    suspend fun deleteTemplate(id: Int) = Api.service.deleteTemplate(id)

    // --- 2FA ---
    suspend fun twoFAStatus(): TwoFAStatus = Api.service.twoFAStatus()
    suspend fun twoFASetup(): TwoFASetup = Api.service.twoFASetup()
    suspend fun twoFAEnable(otp: String): TwoFAStatus = Api.service.twoFAEnable(OtpBody(otp))
    suspend fun twoFADisable(otp: String): TwoFAStatus = Api.service.twoFADisable(OtpBody(otp))

    // --- Field visit (multipart, optional photo) ---
    suspend fun createVisit(
        caseId: Int, lat: Double?, lng: Double?, accuracy: Double?,
        personMoved: Boolean, paid: Boolean, amount: Double,
        disposition: String?, note: String?, photoJpeg: ByteArray?, normStab: String? = null,
        ptpDate: String? = null,
    ): VisitOut {
        fun t(v: String) = v.toRequestBody("text/plain".toMediaType())
        val photoPart = photoJpeg?.let {
            MultipartBody.Part.createFormData(
                "photo", "visit.jpg", it.toRequestBody("image/jpeg".toMediaType()),
            )
        }
        return Api.service.createVisit(
            caseId = t(caseId.toString()),
            latitude = lat?.let { t(it.toString()) },
            longitude = lng?.let { t(it.toString()) },
            gpsAccuracy = accuracy?.let { t(it.toString()) },
            personMoved = t(personMoved.toString()),
            paid = t(paid.toString()),
            amountCollected = t(amount.toString()),
            normStab = normStab?.let { t(it) },
            disposition = disposition?.let { t(it) },
            ptpDate = ptpDate?.let { t(it) },
            note = note?.let { t(it) },
            photo = photoPart,
        )
    }

    // --- My E-ID / profile ---
    suspend fun myProfile(): EmployeeProfile = Api.service.myProfile()

    suspend fun updateMyProfile(patch: Map<String, String?>) {
        Api.service.updateMyProfile(patch)
    }

    /** Set a new password; refreshes the stored token + user so the app continues signed in. */
    suspend fun changePassword(current: String, new: String): Token {
        val t = Api.service.changePassword(ChangePasswordRequest(current, new))
        Api.token = t.accessToken
        session.save(t)
        return t
    }

    // --- Notifications ---
    suspend fun notifications(limit: Int = 30): NotificationList = Api.service.notifications(limit)
    suspend fun markNotificationRead(id: Int) = Api.service.markNotificationRead(id)
    suspend fun markAllNotificationsRead() = Api.service.markAllNotificationsRead()

    /** Caller / head office records the customer's latest address / phone (notifies the FOS). */
    suspend fun contactUpdate(caseId: Int, newAddress: String?, newPhone: String?): Case =
        Api.service.contactUpdate(caseId, mapOf("new_address" to newAddress, "new_phone" to newPhone))
}
