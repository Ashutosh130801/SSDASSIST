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
    @Json(name = "account_no") val accountNo: String? = null,
    @Json(name = "customer_name") val customerName: String? = null,
    val phone: String? = null,
    @Json(name = "alt_phone") val altPhone: String? = null,
    val address: String? = null,
    val pincode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val bucket: String? = null,
    @Json(name = "total_outstanding") val totalOutstanding: Double = 0.0,
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
    val mode: String? = null,
    val reference: String? = null,
)

@JsonClass(generateAdapter = true)
data class CaseUpdate(
    val status: String? = null,
    val disposition: String? = null,
    val remarks: String? = null,
    @Json(name = "follow_up_date") val followUpDate: String? = null,
)
