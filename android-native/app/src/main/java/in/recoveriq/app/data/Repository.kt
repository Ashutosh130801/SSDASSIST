package `in`.recoveriq.app.data

import android.content.Context

/**
 * Thin repository over ApiService. Keeps the in-memory token cache (Api.token)
 * in lockstep with the persisted Session so both UI and the background service authenticate.
 */
class Repository(context: Context) {

    private val session = Session(context.applicationContext)

    suspend fun bootstrapToken() {
        Api.token = session.token()
    }

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

    suspend fun myCases(): List<Case> = Api.service.cases(mine = true)
    suspend fun allCases(status: String? = null, bank: String? = null): List<Case> =
        Api.service.cases(status = status, bank = bank)
    suspend fun case(id: Int): Case = Api.service.case(id)
    suspend fun updateCase(id: Int, update: CaseUpdate): Case = Api.service.updateCase(id, update)
    suspend fun recordPayment(id: Int, amount: Double, mode: String?, ref: String?): Case =
        Api.service.recordPayment(id, PaymentRequest(amount, mode, ref))

    suspend fun liveOfficers(): List<OfficerLocation> = Api.service.liveOfficers()
    suspend fun myTodayRoute(): List<PingOut> = Api.service.myTodayRoute()
    suspend fun officerRoute(id: Int, date: String? = null): List<PingOut> =
        Api.service.officerRoute(id, date)

    suspend fun callQueue(segment: String? = null): List<Case> = Api.service.callQueue(segment)
    suspend fun ptpTracker(): List<Case> = Api.service.ptpTracker()
}
