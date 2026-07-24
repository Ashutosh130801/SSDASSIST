package `in`.recoveriq.app.data

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/**
 * Data classes mirroring the FastAPI backend's Pydantic schemas.
 * Keep these field names in sync with app/backend/app/schemas.py.
 */

@JsonClass(generateAdapter = true)
data class LoginRequest(
    val email: String,
    val password: String,
    @Json(name = "device_id") val deviceId: String? = null,
    @Json(name = "device_label") val deviceLabel: String? = null,
    val otp: String? = null,
)

@JsonClass(generateAdapter = true)
data class Token(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "token_type") val tokenType: String = "bearer",
    val user: User,
)

@JsonClass(generateAdapter = true)
data class User(
    val id: Int,
    val name: String,
    val email: String,
    val role: String = "telecaller",
    val phone: String? = null,
    val branch: String? = null,
    val banks: List<String> = emptyList(),
    @Json(name = "assigned_pincodes") val assignedPincodes: List<String> = emptyList(),
    @Json(name = "photo_url") val photoUrl: String? = null,
    @Json(name = "is_active") val isActive: Boolean = true,
) {
    val isFieldAgent get() = role == "fos"
    val isTelecaller get() = role == "telecaller"
    val isManager get() = role == "manager"
    val isAdmin get() = role == "admin"
    val roleLabel: String
        get() = when (role) {
            "admin" -> "Administrator"
            "manager" -> "Collections Manager"
            "fos" -> "Field Agent"
            "telecaller" -> "Tele-calling Agent"
            else -> role.replaceFirstChar { it.uppercase() }
        }
}

@JsonClass(generateAdapter = true)
data class PingCreate(
    val latitude: Double,
    val longitude: Double,
    val accuracy: Double? = null,
    val speed: Double? = null,
    @Json(name = "active_case_id") val activeCaseId: Int? = null,
)

@JsonClass(generateAdapter = true)
data class PingOut(
    val id: Int,
    @Json(name = "officer_id") val officerId: Int,
    val latitude: Double,
    val longitude: Double,
    val accuracy: Double? = null,
    @Json(name = "active_case_id") val activeCaseId: Int? = null,
    @Json(name = "created_at") val createdAt: String,
)

@JsonClass(generateAdapter = true)
data class RoutePoint(val lat: Double, val lng: Double, val at: String? = null)

@JsonClass(generateAdapter = true)
data class TodayRoute(
    val count: Int = 0,
    @Json(name = "distance_km") val distanceKm: Double = 0.0,
    val points: List<RoutePoint> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class OfficerLocation(
    @Json(name = "officer_id") val officerId: Int,
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val accuracy: Double? = null,
    @Json(name = "active_case_id") val activeCaseId: Int? = null,
    @Json(name = "last_seen") val lastSeen: String,
)

@JsonClass(generateAdapter = true)
data class Case(
    val id: Int,
    val bank: String? = null,
    val branch: String? = null,
    val product: String? = null,
    val segment: String? = null,
    @Json(name = "account_no") val accountNo: String? = null,
    @Json(name = "card_no") val cardNo: String? = null,
    @Json(name = "customer_name") val customerName: String? = null,
    val phone: String? = null,
    @Json(name = "alt_phone") val altPhone: String? = null,
    val address: String? = null,
    val pincode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val bucket: String? = null,
    val cycle: String? = null,
    val month: String? = null,
    @Json(name = "total_outstanding") val totalOutstanding: Double = 0.0,
    @Json(name = "principal_outstanding") val principalOutstanding: Double = 0.0,
    @Json(name = "min_amount_due") val minAmountDue: Double = 0.0,
    @Json(name = "funding_amount") val fundingAmount: Double = 0.0,
    @Json(name = "received_amount") val receivedAmount: Double = 0.0,
    @Json(name = "pending_amount") val pendingAmount: Double = 0.0,
    val status: String? = null,
    @Json(name = "paid_status") val paidStatus: String? = null,
    val disposition: String? = null,
    val remarks: String? = null,
    @Json(name = "assigned_fos_id") val assignedFosId: Int? = null,
    @Json(name = "assigned_caller_id") val assignedCallerId: Int? = null,
    @Json(name = "follow_up_date") val followUpDate: String? = null,
    val propensity: Int? = null,
)

@JsonClass(generateAdapter = true)
data class PaymentRequest(
    val amount: Double,
    val mode: String = "UPI",
    val note: String? = null,
    @Json(name = "norm_stab") val normStab: String? = null,
)

@JsonClass(generateAdapter = true)
data class CaseUpdate(
    val status: String? = null,
    val disposition: String? = null,
    val remarks: String? = null,
    @Json(name = "follow_up_date") val followUpDate: String? = null,
)

// ---- Timeline / activity log ----
@JsonClass(generateAdapter = true)
data class TimelineEvent(
    val type: String,
    val at: String? = null,
    val by: String? = null,
    val title: String,
    val detail: String? = null,
    val lat: Double? = null,
    val lng: Double? = null,
    val photo: String? = null,
    val note: String? = null,
    val amount: Double? = null,
    @Json(name = "ptp_date") val ptpDate: String? = null,
)

// ---- Calls ----
@JsonClass(generateAdapter = true)
data class CallCreate(
    @Json(name = "case_id") val caseId: Int,
    val disposition: String,
    @Json(name = "ptp_amount") val ptpAmount: Double = 0.0,
    @Json(name = "ptp_date") val ptpDate: String? = null,
    @Json(name = "follow_up_date") val followUpDate: String? = null,
    @Json(name = "paid_amount") val paidAmount: Double = 0.0,
    @Json(name = "norm_stab") val normStab: String? = null,
    val note: String? = null,
)

@JsonClass(generateAdapter = true)
data class CallOut(
    val id: Int,
    @Json(name = "case_id") val caseId: Int,
    @Json(name = "caller_id") val callerId: Int,
    val disposition: String,
    @Json(name = "ptp_amount") val ptpAmount: Double = 0.0,
    @Json(name = "ptp_date") val ptpDate: String? = null,
    val note: String? = null,
    @Json(name = "created_at") val createdAt: String,
)

// ---- Telecaller queue (structured) ----
@JsonClass(generateAdapter = true)
data class QueueResponse(
    val due: List<Case> = emptyList(),
    @Json(name = "contacted_today") val contactedToday: List<Case> = emptyList(),
    val upcoming: List<Case> = emptyList(),
    val counts: Map<String, Int> = emptyMap(),
)

@JsonClass(generateAdapter = true)
data class PtpRow(
    val case: Case,
    @Json(name = "ptp_amount") val ptpAmount: Double? = null,
    @Json(name = "promised_date") val promisedDate: String? = null,
    val bucket: String,
)

@JsonClass(generateAdapter = true)
data class PtpResponse(
    val rows: List<PtpRow> = emptyList(),
    val counts: Map<String, Int> = emptyMap(),
)

// ---- Templates (WhatsApp/SMS) ----
@JsonClass(generateAdapter = true)
data class Template(
    val id: Int,
    val name: String,
    val channel: String,
    val body: String,
)

@JsonClass(generateAdapter = true)
data class TemplateCreate(
    val name: String,
    val channel: String = "whatsapp",
    val body: String,
)

@JsonClass(generateAdapter = true)
data class CommLog(
    @Json(name = "case_id") val caseId: Int,
    val channel: String = "whatsapp",
    val text: String? = null,
)

// ---- Visits (field) ----
@JsonClass(generateAdapter = true)
data class VisitCreate(
    @Json(name = "case_id") val caseId: Int,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @Json(name = "gps_accuracy") val gpsAccuracy: Double? = null,
    @Json(name = "location_correct") val locationCorrect: Boolean? = null,
    @Json(name = "person_moved") val personMoved: Boolean = false,
    val paid: Boolean = false,
    @Json(name = "amount_collected") val amountCollected: Double = 0.0,
    val disposition: String? = null,
    val note: String? = null,
)

@JsonClass(generateAdapter = true)
data class VisitOut(
    val id: Int,
    @Json(name = "case_id") val caseId: Int,
    @Json(name = "officer_id") val officerId: Int,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @Json(name = "photo_path") val photoPath: String? = null,
    @Json(name = "location_correct") val locationCorrect: Boolean? = null,
    @Json(name = "person_moved") val personMoved: Boolean? = null,
    val paid: Boolean? = null,
    @Json(name = "amount_collected") val amountCollected: Double = 0.0,
    val disposition: String? = null,
    val note: String? = null,
    @Json(name = "created_at") val createdAt: String,
)

// ---- AI Assist ----
@JsonClass(generateAdapter = true)
data class AIRequest(val prompt: String, val context: String? = null)

@JsonClass(generateAdapter = true)
data class AIResponse(val reply: String)

// ---- Dashboard analytics ----
@JsonClass(generateAdapter = true)
data class DashboardKpis(
    @Json(name = "total_cases") val totalCases: Int = 0,
    val target: Double = 0.0,
    val received: Double = 0.0,
    val pending: Double = 0.0,
    @Json(name = "recovery_rate") val recoveryRate: Double = 0.0,
    val paid: Int = 0,
    val unpaid: Int = 0,
    val partial: Int = 0,
)

@JsonClass(generateAdapter = true)
data class BankRow(val bank: String, val cases: Int, val received: Double, val pending: Double)

@JsonClass(generateAdapter = true)
data class StatusRow(val status: String, val count: Int)

@JsonClass(generateAdapter = true)
data class DispRow(val disposition: String, val count: Int)

@JsonClass(generateAdapter = true)
data class TrendPoint(val date: String, val collected: Double, val visits: Int)

@JsonClass(generateAdapter = true)
data class LeaderRow(val name: String, val visits: Int, val collected: Double)

@JsonClass(generateAdapter = true)
data class DashboardResponse(
    val kpis: DashboardKpis = DashboardKpis(),
    @Json(name = "by_bank") val byBank: List<BankRow> = emptyList(),
    @Json(name = "by_status") val byStatus: List<StatusRow> = emptyList(),
    @Json(name = "by_disposition") val byDisposition: List<DispRow> = emptyList(),
    val trend: List<TrendPoint> = emptyList(),
    @Json(name = "fo_leaderboard") val leaderboard: List<LeaderRow> = emptyList(),
)

// ---- Activity feed ----
@JsonClass(generateAdapter = true)
data class ActivityItem(
    val type: String,
    val at: String? = null,
    @Json(name = "case_id") val caseId: Int? = null,
    val customer: String? = null,
    val bank: String? = null,
    val by: String? = null,
    val amount: Double? = null,
    val detail: String? = null,
    val note: String? = null,
    val lat: Double? = null,
    val lng: Double? = null,
    val photo: String? = null,
    @Json(name = "off_location") val offLocation: Boolean? = null,
)

// ---- Litigation / legal ----
@JsonClass(generateAdapter = true)
data class Legal(
    val id: Int,
    @Json(name = "case_id") val caseId: Int? = null,
    @Json(name = "borrower_name") val borrowerName: String? = null,
    val bank: String? = null,
    @Json(name = "matter_type") val matterType: String? = null,
    val court: String? = null,
    @Json(name = "case_number") val caseNumber: String? = null,
    val stage: String? = null,
    @Json(name = "filed_date") val filedDate: String? = null,
    @Json(name = "next_hearing_date") val nextHearingDate: String? = null,
    val status: String = "open",
    val amount: Double = 0.0,
    val notes: String? = null,
    val branch: String? = null,
)

@JsonClass(generateAdapter = true)
data class LegalCreate(
    @Json(name = "matter_type") val matterType: String,
    @Json(name = "borrower_name") val borrowerName: String? = null,
    val bank: String? = null,
    val court: String? = null,
    @Json(name = "case_number") val caseNumber: String? = null,
    val stage: String? = null,
    @Json(name = "next_hearing_date") val nextHearingDate: String? = null,
    val status: String = "open",
    val amount: Double = 0.0,
    val notes: String? = null,
)

@JsonClass(generateAdapter = true)
data class LegalInsights(
    val open: Int = 0,
    @Json(name = "hearing_overdue") val hearingOverdue: Int = 0,
    @Json(name = "hearing_today") val hearingToday: Int = 0,
    @Json(name = "hearing_week") val hearingWeek: Int = 0,
)

// ---- Leave ----
@JsonClass(generateAdapter = true)
data class Leave(
    val id: Int,
    @Json(name = "user_id") val userId: Int,
    @Json(name = "leave_type") val leaveType: String? = null,
    @Json(name = "start_date") val startDate: String,
    @Json(name = "end_date") val endDate: String,
    val days: Int,
    val reason: String? = null,
    val status: String,
    @Json(name = "user_name") val userName: String? = null,
    @Json(name = "user_branch") val userBranch: String? = null,
    @Json(name = "approver_name") val approverName: String? = null,
)

@JsonClass(generateAdapter = true)
data class LeaveCreate(
    @Json(name = "leave_type") val leaveType: String,
    @Json(name = "start_date") val startDate: String,
    @Json(name = "end_date") val endDate: String,
    val reason: String? = null,
)

@JsonClass(generateAdapter = true)
data class LeaveBalance(
    val type: String,
    val allowance: Int? = null,
    val used: Int = 0,
    val pending: Int = 0,
    val remaining: Int? = null,
)

// ---- Devices ----
@JsonClass(generateAdapter = true)
data class Device(
    val id: Int,
    @Json(name = "user_id") val userId: Int,
    @Json(name = "device_id") val deviceId: String,
    val label: String? = null,
    val approved: Boolean = false,
    @Json(name = "user_name") val userName: String? = null,
    @Json(name = "user_branch") val userBranch: String? = null,
)

// ---- 2FA ----
@JsonClass(generateAdapter = true)
data class TwoFAStatus(val enabled: Boolean = false)

@JsonClass(generateAdapter = true)
data class TwoFASetup(val secret: String, @Json(name = "otpauth_url") val otpauthUrl: String)

@JsonClass(generateAdapter = true)
data class OtpBody(val otp: String)

// ---- User management ----
@JsonClass(generateAdapter = true)
data class UserCreate(
    val name: String,
    val email: String,
    val password: String,
    val role: String = "telecaller",
    val phone: String? = null,
    val branch: String? = null,
    val banks: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class UserUpdate(
    val name: String? = null,
    val phone: String? = null,
    val role: String? = null,
    val branch: String? = null,
    @Json(name = "is_active") val isActive: Boolean? = null,
    val password: String? = null,
)
