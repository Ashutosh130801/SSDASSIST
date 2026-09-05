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
    @Json(name = "must_change_password") val mustChangePassword: Boolean = false,
    @Json(name = "profile_completed") val profileCompleted: Boolean = false,
    val designation: String? = null,
    val location: String? = null,
    // Dual role (caller/FOS who is also a team lead)
    @Json(name = "also_team_lead") val alsoTeamLead: Boolean = false,
    @Json(name = "tl_emp_code") val tlEmpCode: String? = null,
    @Json(name = "available_views") val availableViews: List<String> = emptyList(),
    @Json(name = "active_view") val activeView: String? = null,
) {
    val isFieldAgent get() = role == "fos"
    val isTelecaller get() = role == "telecaller"
    val isManager get() = role == "manager"
    val isAdmin get() = role == "admin"
    val isTeamLead get() = role == "teamlead"
    val roleLabel: String
        get() = when (role) {
            "admin" -> "Administrator"
            "manager" -> "Collections Manager"
            "teamlead" -> "Team Lead"
            "fos" -> "Field Agent"
            "telecaller" -> "Tele-calling Agent"
            "headoffice" -> "Head Office"
            "backend" -> "Back-office Official"
            "hr" -> "HR"
            "it" -> "IT"
            "staff" -> "Staff"
            else -> role.replaceFirstChar { it.uppercase() }
        }
}

// ---- Team-lead dashboard ----
@JsonClass(generateAdapter = true)
data class TeamLeadInfo(val id: Int = 0, val name: String = "", val branch: String? = null)

@JsonClass(generateAdapter = true)
data class TeamKpis(
    val members: Int = 0, val fos: Int = 0, val callers: Int = 0,
    val cases: Int = 0, val resolved: Int = 0,
    @Json(name = "total_enr") val totalEnr: Double = 0.0,
    val recovered: Double = 0.0, val pending: Double = 0.0,
    @Json(name = "recovery_pct") val recoveryPct: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class MemberToday(
    val label: String? = null, val count: Int = 0, val ptp: Int? = null, val collected: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class TeamMemberCard(
    val id: Int = 0, val name: String = "", val role: String = "",
    @Json(name = "emp_code") val empCode: String? = null,
    val phone: String? = null, val email: String? = null,
    val assigned: Int = 0, val resolved: Int = 0,
    val recovered: Double = 0.0, val pending: Double = 0.0,
    @Json(name = "recovery_pct") val recoveryPct: Double = 0.0,
    val today: MemberToday? = null,
)

@JsonClass(generateAdapter = true)
data class TeamOverview(
    val lead: TeamLeadInfo? = null,
    val members: List<TeamMemberCard> = emptyList(),
    val kpis: TeamKpis = TeamKpis(),
    val leaderboard: List<TeamMemberCard> = emptyList(),
)

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
    @Json(name = "new_address") val newAddress: String? = null,
    @Json(name = "new_phone") val newPhone: String? = null,
    @Json(name = "new_contact_by") val newContactBy: String? = null,
    @Json(name = "new_contact_at") val newContactAt: String? = null,
    val pincode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @Json(name = "geo_precision") val geoPrecision: String? = null,     // rooftop/locality/pincode/city
    @Json(name = "location_source") val locationSource: String? = null, // geocoded | field
    @Json(name = "address_clean") val addressClean: String? = null,
    val digipin: String? = null,
    val bucket: String? = null,
    val cycle: String? = null,
    val month: String? = null,
    @Json(name = "total_outstanding") val totalOutstanding: Double = 0.0,
    @Json(name = "principal_outstanding") val principalOutstanding: Double = 0.0,
    @Json(name = "min_amount_due") val minAmountDue: Double = 0.0,
    @Json(name = "funding_amount") val fundingAmount: Double = 0.0,
    @Json(name = "received_amount") val receivedAmount: Double = 0.0,
    @Json(name = "pending_amount") val pendingAmount: Double = 0.0,
    @Json(name = "enr") val enr: Double = 0.0,
    @Json(name = "norm_amount") val normAmount: Double = 0.0,
    @Json(name = "stab_amount") val stabAmount: Double = 0.0,
    @Json(name = "norm_stab") val normStab: String? = null,
    @Json(name = "is_settlement_case") val isSettlementCase: Boolean = false,
    @Json(name = "remaining_to_norm") val remainingToNorm: Double? = null,   // pending NORM
    @Json(name = "remaining_to_stab") val remainingToStab: Double? = null,   // pending STAB
    @Json(name = "auto_debit") val autoDebit: Boolean = false,
    val status: String? = null,
    @Json(name = "paid_status") val paidStatus: String? = null,
    val disposition: String? = null,
    val remarks: String? = null,
    @Json(name = "caller_name") val callerName: String? = null,
    @Json(name = "fos_name") val fosName: String? = null,
    val team: String? = null,
    @Json(name = "team_lead") val teamLead: String? = null,
    val cat: String? = null,
    @Json(name = "assigned_fos_id") val assignedFosId: Int? = null,
    @Json(name = "assigned_caller_id") val assignedCallerId: Int? = null,
    @Json(name = "assigned_fos_name") val assignedFosName: String? = null,
    @Json(name = "assigned_fos_phone") val assignedFosPhone: String? = null,
    @Json(name = "assigned_fos_code") val assignedFosCode: String? = null,
    @Json(name = "assigned_caller_name") val assignedCallerName: String? = null,
    @Json(name = "assigned_caller_phone") val assignedCallerPhone: String? = null,
    @Json(name = "assigned_caller_code") val assignedCallerCode: String? = null,
    @Json(name = "follow_up_date") val followUpDate: String? = null,
    @Json(name = "last_contacted_at") val lastContactedAt: String? = null,
    val visited: Boolean? = false,
    @Json(name = "visited_today") val visitedToday: Boolean? = false,
    @Json(name = "contacted_today") val contactedToday: Boolean? = false,
    val escalated: Boolean? = false,
    @Json(name = "esc_prev_fos_id") val escPrevFosId: Int? = null,
    @Json(name = "esc_prev_caller_id") val escPrevCallerId: Int? = null,
    @Json(name = "review_color") val reviewColor: String? = null,   // my personal highlight colour
    @Json(name = "review_note") val reviewNote: String? = null,
    val propensity: Int? = null,
    val flagged: Boolean? = false,
    @Json(name = "flag_reason") val flagReason: String? = null,
) {
    /** Working state for FOS/caller lists: fresh (untouched) → touched today → paid. */
    val workState: String
        get() = when {
            (paidStatus ?: "") == "PAID" || status == "paid" -> "paid"
            visitedToday == true || contactedToday == true || status == "in_progress" || status == "ptp" || status == "callback" -> "touched"
            else -> "fresh"
        }
}

@JsonClass(generateAdapter = true)
data class ReminderItem(
    @Json(name = "case_id") val caseId: Int,
    val customer: String? = null,
    val account: String? = null,
    val bank: String? = null,
    val phone: String? = null,
    @Json(name = "ptp_date") val ptpDate: String? = null,
    val pending: Double = 0.0,
    val overdue: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class RemindersResponse(
    val date: String? = null,
    val count: Int = 0,
    val overdue: Int = 0,
    @Json(name = "due_today") val dueToday: Int = 0,
    val rows: List<ReminderItem> = emptyList(),
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

// One merged note/remark (call or visit), tagged with who wrote it and when.
@JsonClass(generateAdapter = true)
data class CaseNote(
    val by: String? = null,
    val role: String? = null,
    val source: String? = null,        // "call" | "visit"
    val disposition: String? = null,
    val text: String? = null,
    @Json(name = "when") val at: String? = null,
)

@JsonClass(generateAdapter = true)
data class PtpRow(
    val case: Case,
    @Json(name = "ptp_amount") val ptpAmount: Double? = null,
    @Json(name = "promised_date") val promisedDate: String? = null,
    val bucket: String,
    val notes: List<CaseNote> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class StaffOpt(
    val id: Int,
    val name: String? = null,
    @Json(name = "emp_code") val empCode: String? = null,
) {
    val label: String get() = (name ?: "#$id") + (empCode?.let { " ($it)" } ?: "")
}

@JsonClass(generateAdapter = true)
data class PtpResponse(
    val rows: List<PtpRow> = emptyList(),
    val counts: Map<String, Int> = emptyMap(),
    val callers: List<StaffOpt> = emptyList(),
    val fos: List<StaffOpt> = emptyList(),
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
    @Json(name = "cash_collected") val cashCollected: Double = 0.0,
    val paid: Int = 0,
    val unpaid: Int = 0,
    val partial: Int = 0,
)

@JsonClass(generateAdapter = true)
data class BankRow(val bank: String, val cases: Int, val received: Double, val pending: Double)

@JsonClass(generateAdapter = true)
data class StatusRow(val status: String, val count: Int)

@JsonClass(generateAdapter = true)
data class PipelineRow(val key: String, val count: Int)

// ---- Attendance ----
@JsonClass(generateAdapter = true)
data class AttPresence(
    val state: String = "offline",
    val platform: String? = null,
    @Json(name = "last_seen") val lastSeen: String? = null,
    @Json(name = "idle_seconds") val idleSeconds: Int = 0,
)

@JsonClass(generateAdapter = true)
data class AttRow(
    @Json(name = "user_id") val userId: Int = 0,
    val name: String? = null,
    @Json(name = "emp_code") val empCode: String? = null,
    val role: String? = null,
    val status: String = "absent",
    val late: Boolean = false,
    @Json(name = "check_in_at") val checkInAt: String? = null,
    @Json(name = "check_out_at") val checkOutAt: String? = null,
    @Json(name = "check_in_lat") val checkInLat: Double? = null,
    @Json(name = "check_in_lng") val checkInLng: Double? = null,
    @Json(name = "live_lat") val liveLat: Double? = null,
    @Json(name = "live_lng") val liveLng: Double? = null,
    @Json(name = "live_at") val liveAt: String? = null,
    @Json(name = "worked_seconds") val workedSeconds: Int = 0,
    @Json(name = "idle_seconds") val idleSeconds: Int = 0,
    @Json(name = "auto_checkout") val autoCheckout: Boolean = false,
    val calls: Int = 0, val visits: Int = 0, val collected: Double = 0.0,
    @Json(name = "show_activity") val showActivity: Boolean = false,
    @Json(name = "team_total") val teamTotal: Boolean = false,
    val presence: AttPresence = AttPresence(),
)

@JsonClass(generateAdapter = true)
data class MeToday(
    val tracked: Boolean = false,
    @Json(name = "needs_checkin") val needsCheckin: Boolean = false,
    @Json(name = "after_hours") val afterHours: Boolean = false,   // logged in past shift end, not checked in
    @Json(name = "shift_start") val shiftStart: String = "09:00",
    @Json(name = "shift_end") val shiftEnd: String = "19:00",
    @Json(name = "late_after") val lateAfter: String = "10:00",
    val attendance: AttRow = AttRow(),
)

@JsonClass(generateAdapter = true)
data class HeartbeatResp(
    @Json(name = "prompt_overtime") val promptOvertime: Boolean = false,
    @Json(name = "auto_logout") val autoLogout: Boolean = false,
    @Json(name = "minutes_to_shift_end") val minutesToShiftEnd: Int? = null,
    @Json(name = "checked_out") val checkedOut: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class AttDaySummary(
    val present: Int = 0, val late: Int = 0, val absent: Int = 0,
    val leave: Int = 0, val online: Int = 0, val total: Int = 0,
)

@JsonClass(generateAdapter = true)
data class AttDay(
    val date: String = "",
    val rows: List<AttRow> = emptyList(),
    val summary: AttDaySummary = AttDaySummary(),
    @Json(name = "can_download") val canDownload: Boolean = false,
)

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
    val pipeline: List<PipelineRow> = emptyList(),   // derived funnel: new/allocated/in_progress/ptp/paid
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

// ---- Profile change requests ----
@JsonClass(generateAdapter = true)
data class ChangeField(
    val field: String,
    val label: String,
    val current: String? = null,
)

@JsonClass(generateAdapter = true)
data class ProfileChangeRequest(
    val id: Int,
    @Json(name = "user_id") val userId: Int? = null,
    @Json(name = "user_name") val userName: String? = null,
    @Json(name = "user_code") val userCode: String? = null,
    @Json(name = "user_branch") val userBranch: String? = null,
    val field: String,
    @Json(name = "field_label") val fieldLabel: String? = null,
    @Json(name = "old_value") val oldValue: String? = null,
    @Json(name = "new_value") val newValue: String? = null,
    val note: String? = null,
    val status: String,
    @Json(name = "review_note") val reviewNote: String? = null,
    @Json(name = "reviewer_name") val reviewerName: String? = null,
    @Json(name = "created_at") val createdAt: String? = null,
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

// ---- Employee E-ID / profile (GET/PATCH /api/manpower/me) ----
@JsonClass(generateAdapter = true)
data class EmployeeProfile(
    val id: Int = 0,
    @Json(name = "emp_code") val empCode: String? = null,
    @Json(name = "hr_ref") val hrRef: String? = null,
    val name: String = "",
    val email: String? = null,
    val phone: String? = null,
    val role: String = "",
    val designation: String? = null,
    val location: String? = null,
    val branch: String? = null,
    val gender: String? = null,
    val dob: String? = null,
    @Json(name = "joining_date") val joiningDate: String? = null,
    @Json(name = "blood_group") val bloodGroup: String? = null,
    @Json(name = "marital_status") val maritalStatus: String? = null,
    @Json(name = "emergency_contact") val emergencyContact: String? = null,
    @Json(name = "emergency_name") val emergencyName: String? = null,
    @Json(name = "emergency_relation") val emergencyRelation: String? = null,
    @Json(name = "aadhar_number") val aadharNumber: String? = null,
    @Json(name = "pan_number") val panNumber: String? = null,
    @Json(name = "bank_holder") val bankHolder: String? = null,
    @Json(name = "bank_account") val bankAccount: String? = null,
    @Json(name = "ifsc_code") val ifscCode: String? = null,
    @Json(name = "bank_name") val bankName: String? = null,
    @Json(name = "current_address") val currentAddress: String? = null,
    @Json(name = "photo_url") val photoUrl: String? = null,
    @Json(name = "profile_completed") val profileCompleted: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class ChangePasswordRequest(
    @Json(name = "current_password") val currentPassword: String,
    @Json(name = "new_password") val newPassword: String,
)

@JsonClass(generateAdapter = true)
data class NotificationItem(
    val id: Int = 0,
    @Json(name = "case_id") val caseId: Int? = null,
    val type: String? = null,
    val title: String? = null,
    val body: String? = null,
    val read: Boolean = false,
    @Json(name = "created_by") val createdBy: String? = null,
    @Json(name = "created_at") val createdAt: String? = null,
)

@JsonClass(generateAdapter = true)
data class NotificationList(
    val unread: Int = 0,
    val items: List<NotificationItem> = emptyList(),
)

// FTD (today) / MTD (month-till-day) / LMTD (last month-till-day) / Overall cash collected.
@JsonClass(generateAdapter = true)
data class Trends(
    val ftd: Double = 0.0,
    val mtd: Double = 0.0,
    val lmtd: Double = 0.0,
    val overall: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class EmployeeTrends(
    @Json(name = "user_id") val userId: Int = 0,
    val name: String? = null,
    @Json(name = "emp_code") val empCode: String? = null,
    val cases: Int = 0,
    val trends: Trends = Trends(),
)

// ---- Bank-first portfolio navigation (banks → products → cases) ----
@JsonClass(generateAdapter = true)
data class PortfolioBank(
    val bank: String = "—",
    @Json(name = "logo_domain") val logoDomain: String? = null,
    @Json(name = "product_count") val productCount: Int = 0,
    val count: Int = 0,
    val received: Double = 0.0,
    val pending: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class BranchBucket(
    val branch: String = "",
    val count: Int = 0,
    val received: Double = 0.0,
    val pending: Double = 0.0,
    val paid: Int = 0,
    val unpaid: Int = 0,
    @Json(name = "count_current") val countCurrent: Int = 0,
    @Json(name = "count_next") val countNext: Int = 0,
)

@JsonClass(generateAdapter = true)
data class ProductSummary(
    val bank: String = "—",
    val product: String = "—",
    val segment: String? = null,
    val branch: String = "",
    @Json(name = "branch_split") val branchSplit: Boolean = false,
    val count: Int = 0,
    val received: Double = 0.0,
    val pending: Double = 0.0,
    val paid: Int = 0,
    val unpaid: Int = 0,
    @Json(name = "count_current") val countCurrent: Int = 0,
    @Json(name = "count_next") val countNext: Int = 0,
    val branches: List<BranchBucket> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class FilterPerson(val id: Int = 0, val name: String? = null, val code: String? = null)

@JsonClass(generateAdapter = true)
data class FilterOptions(
    val cycles: List<String> = emptyList(),
    val fos: List<FilterPerson> = emptyList(),
    val callers: List<FilterPerson> = emptyList(),
)

// ---- Individual performance screen (opened from a clickable FOS/caller name) ----
@JsonClass(generateAdapter = true)
data class PerfTotals(
    val count: Int = 0, val paid: Int = 0, val unpaid: Int = 0,
    val enr: Double = 0.0, @Json(name = "paid_enr") val paidEnr: Double = 0.0,
    val pending: Double = 0.0, val collected: Double = 0.0, val pos: Double = 0.0,
    @Json(name = "achieved_pct") val achievedPct: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class PerfActivity(
    val calls: Int = 0, val contacted: Int = 0,
    val visits: Int = 0, @Json(name = "visits_paid") val visitsPaid: Int = 0, val visited: Int = 0,
    val collected: Double = 0.0,   // rupees collected via their own call/visit logs (event-based)
)

// One row in the portfolio-wise leaderboard (peers on the same portfolio, ranked by paid ENR).
@JsonClass(generateAdapter = true)
data class PerfLeaderRow(
    val rank: Int = 0, val name: String = "", val you: Boolean = false,
    val count: Int = 0, val enr: Double = 0.0,
    @Json(name = "paid_enr") val paidEnr: Double = 0.0,
    @Json(name = "achieved_pct") val achievedPct: Double = 0.0,
    val collected: Double = 0.0,
)

@JsonClass(generateAdapter = true)
data class PerfPortfolio(
    val label: String = "", val count: Int = 0, val paid: Int = 0, val unpaid: Int = 0,
    val enr: Double = 0.0, @Json(name = "paid_enr") val paidEnr: Double = 0.0,
    val pending: Double = 0.0, val pos: Double = 0.0, val collected: Double = 0.0,
    @Json(name = "achieved_pct") val achievedPct: Double = 0.0,
    @Json(name = "target_pct") val targetPct: Double = 0.0,
    @Json(name = "to_target_pct") val toTargetPct: Double = 0.0,
    val rank: Int? = null, @Json(name = "field_size") val fieldSize: Int = 0,
    val activity: PerfActivity = PerfActivity(),
    val trends: Trends = Trends(),
    val leaderboard: List<PerfLeaderRow> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class Performance(
    val name: String? = null,
    @Json(name = "emp_code") val empCode: String? = null,
    @Json(name = "as_fos") val asFos: Boolean = false,
    val totals: PerfTotals = PerfTotals(),
    val activity: PerfActivity = PerfActivity(),
    val trends: Trends = Trends(),
    val portfolios: List<PerfPortfolio> = emptyList(),
)
