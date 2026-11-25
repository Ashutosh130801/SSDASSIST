import Foundation

// =====================================================================================
// RecoverIQ models — 1:1 port of android-native data/Models.kt (Moshi data classes).
//
// DEFAULT-HANDLING APPROACH (read this before using the models):
//  * Every struct has explicit CodingKeys (JSON names from Kotlin @Json(name=…)), an explicit
//    memberwise `init(...)` whose parameters carry the Kotlin defaults (so
//    `CallCreate(caseId: 1, disposition: "PTP")` works), and an explicit `init(from:)`.
//  * `init(from:)` uses the lenient helpers in JSONValue.swift:
//      c.d(.x, 0.0)      Kotlin `val x: Double = 0.0`  → NON-optional Swift `Double`; missing/null → default
//      c.opt(.y)         Kotlin `val y: String?`       → optional; missing/null/garbage → nil
//      c.optOr(.z, false) Kotlin `val z: Boolean? = false` → optional; missing → false, null → nil
//      try c.req(.id)    Kotlin required non-null      → throws if missing (same as Moshi)
//    Numeric/string mismatches are coerced ("12" → 12, 5 → "5").
//  * Encodable is synthesized from the same CodingKeys; nil optionals are omitted (like Moshi).
//  * Property names are IDENTICAL to Kotlin. Swift keywords are back-ticked in declarations
//    (`PtpRow.case`) but can be used plainly after a dot: `row.case.customerName`.
//  * All models are `Codable, Hashable`; those with `id: Int` are also `Identifiable`.
//  * Computed helpers (User.isFieldAgent / roleLabel, Case.workState, StaffOpt.label) are at the
//    bottom of this file. Generated parts continue in Models2.swift … Models{N}.swift.
//  * Need another model? Add `Core/Models+<Group>.swift` — never edit these files.
// =====================================================================================

struct CaseExportRequest: Codable, Hashable {
    var ids: [Int]
    var fmt: String
    var title: String?

    enum CodingKeys: String, CodingKey {
        case ids
        case fmt
        case title
    }

    init(ids: [Int], fmt: String, title: String? = nil) {
        self.ids = ids
        self.fmt = fmt
        self.title = title
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.ids = try c.req(.ids)
        self.fmt = try c.req(.fmt)
        self.title = c.opt(.title)
    }
}

struct LoginRequest: Codable, Hashable {
    var email: String
    var password: String
    var deviceId: String?
    var deviceLabel: String?
    var otp: String?

    enum CodingKeys: String, CodingKey {
        case email
        case password
        case deviceId = "device_id"
        case deviceLabel = "device_label"
        case otp
    }

    init(email: String, password: String, deviceId: String? = nil, deviceLabel: String? = nil, otp: String? = nil) {
        self.email = email
        self.password = password
        self.deviceId = deviceId
        self.deviceLabel = deviceLabel
        self.otp = otp
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.email = try c.req(.email)
        self.password = try c.req(.password)
        self.deviceId = c.opt(.deviceId)
        self.deviceLabel = c.opt(.deviceLabel)
        self.otp = c.opt(.otp)
    }
}

struct Token: Codable, Hashable {
    var accessToken: String
    var tokenType: String
    var user: User

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case user
    }

    init(accessToken: String, tokenType: String = "bearer", user: User) {
        self.accessToken = accessToken
        self.tokenType = tokenType
        self.user = user
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.accessToken = try c.req(.accessToken)
        self.tokenType = c.d(.tokenType, "bearer")
        self.user = try c.req(.user)
    }
}

struct User: Codable, Hashable, Identifiable {
    var id: Int
    var name: String
    var email: String
    var role: String
    var phone: String?
    var branch: String?
    var banks: [String]
    var assignedPincodes: [String]
    var photoUrl: String?
    var isActive: Bool
    var mustChangePassword: Bool
    var profileCompleted: Bool
    var designation: String?
    var location: String?
    var alsoTeamLead: Bool
    var tlEmpCode: String?
    var alsoFieldAgent: Bool
    var fosEmpCode: String?
    var alsoCaller: Bool
    var tcEmpCode: String?
    var availableViews: [String]
    var activeView: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case email
        case role
        case phone
        case branch
        case banks
        case assignedPincodes = "assigned_pincodes"
        case photoUrl = "photo_url"
        case isActive = "is_active"
        case mustChangePassword = "must_change_password"
        case profileCompleted = "profile_completed"
        case designation
        case location
        case alsoTeamLead = "also_team_lead"
        case tlEmpCode = "tl_emp_code"
        case alsoFieldAgent = "also_field_agent"
        case fosEmpCode = "fos_emp_code"
        case alsoCaller = "also_caller"
        case tcEmpCode = "tc_emp_code"
        case availableViews = "available_views"
        case activeView = "active_view"
    }

    init(id: Int, name: String, email: String, role: String = "telecaller", phone: String? = nil, branch: String? = nil, banks: [String] = [], assignedPincodes: [String] = [], photoUrl: String? = nil, isActive: Bool = true, mustChangePassword: Bool = false, profileCompleted: Bool = false, designation: String? = nil, location: String? = nil, alsoTeamLead: Bool = false, tlEmpCode: String? = nil, alsoFieldAgent: Bool = false, fosEmpCode: String? = nil, alsoCaller: Bool = false, tcEmpCode: String? = nil, availableViews: [String] = [], activeView: String? = nil) {
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.phone = phone
        self.branch = branch
        self.banks = banks
        self.assignedPincodes = assignedPincodes
        self.photoUrl = photoUrl
        self.isActive = isActive
        self.mustChangePassword = mustChangePassword
        self.profileCompleted = profileCompleted
        self.designation = designation
        self.location = location
        self.alsoTeamLead = alsoTeamLead
        self.tlEmpCode = tlEmpCode
        self.alsoFieldAgent = alsoFieldAgent
        self.fosEmpCode = fosEmpCode
        self.alsoCaller = alsoCaller
        self.tcEmpCode = tcEmpCode
        self.availableViews = availableViews
        self.activeView = activeView
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.name = try c.req(.name)
        self.email = try c.req(.email)
        self.role = c.d(.role, "telecaller")
        self.phone = c.opt(.phone)
        self.branch = c.opt(.branch)
        self.banks = c.d(.banks, [])
        self.assignedPincodes = c.d(.assignedPincodes, [])
        self.photoUrl = c.opt(.photoUrl)
        self.isActive = c.d(.isActive, true)
        self.mustChangePassword = c.d(.mustChangePassword, false)
        self.profileCompleted = c.d(.profileCompleted, false)
        self.designation = c.opt(.designation)
        self.location = c.opt(.location)
        self.alsoTeamLead = c.d(.alsoTeamLead, false)
        self.tlEmpCode = c.opt(.tlEmpCode)
        self.alsoFieldAgent = c.d(.alsoFieldAgent, false)
        self.fosEmpCode = c.opt(.fosEmpCode)
        self.alsoCaller = c.d(.alsoCaller, false)
        self.tcEmpCode = c.opt(.tcEmpCode)
        self.availableViews = c.d(.availableViews, [])
        self.activeView = c.opt(.activeView)
    }
}

struct TeamLeadInfo: Codable, Hashable, Identifiable {
    var id: Int
    var name: String
    var branch: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case branch
    }

    init(id: Int = 0, name: String = "", branch: String? = nil) {
        self.id = id
        self.name = name
        self.branch = branch
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.name = c.d(.name, "")
        self.branch = c.opt(.branch)
    }
}

struct TeamKpis: Codable, Hashable {
    var members: Int
    var fos: Int
    var callers: Int
    var cases: Int
    var resolved: Int
    var totalEnr: Double
    var recovered: Double
    var pending: Double
    var recoveryPct: Double

    enum CodingKeys: String, CodingKey {
        case members
        case fos
        case callers
        case cases
        case resolved
        case totalEnr = "total_enr"
        case recovered
        case pending
        case recoveryPct = "recovery_pct"
    }

    init(members: Int = 0, fos: Int = 0, callers: Int = 0, cases: Int = 0, resolved: Int = 0, totalEnr: Double = 0.0, recovered: Double = 0.0, pending: Double = 0.0, recoveryPct: Double = 0.0) {
        self.members = members
        self.fos = fos
        self.callers = callers
        self.cases = cases
        self.resolved = resolved
        self.totalEnr = totalEnr
        self.recovered = recovered
        self.pending = pending
        self.recoveryPct = recoveryPct
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.members = c.d(.members, 0)
        self.fos = c.d(.fos, 0)
        self.callers = c.d(.callers, 0)
        self.cases = c.d(.cases, 0)
        self.resolved = c.d(.resolved, 0)
        self.totalEnr = c.d(.totalEnr, 0.0)
        self.recovered = c.d(.recovered, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.recoveryPct = c.d(.recoveryPct, 0.0)
    }
}

struct MemberToday: Codable, Hashable {
    var label: String?
    var count: Int
    var ptp: Int?
    var collected: Double

    enum CodingKeys: String, CodingKey {
        case label
        case count
        case ptp
        case collected
    }

    init(label: String? = nil, count: Int = 0, ptp: Int? = nil, collected: Double = 0.0) {
        self.label = label
        self.count = count
        self.ptp = ptp
        self.collected = collected
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.label = c.opt(.label)
        self.count = c.d(.count, 0)
        self.ptp = c.opt(.ptp)
        self.collected = c.d(.collected, 0.0)
    }
}

struct TeamMemberCard: Codable, Hashable, Identifiable {
    var id: Int
    var name: String
    var role: String
    var empCode: String?
    var phone: String?
    var email: String?
    var assigned: Int
    var resolved: Int
    var recovered: Double
    var pending: Double
    var recoveryPct: Double
    var today: MemberToday?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case role
        case empCode = "emp_code"
        case phone
        case email
        case assigned
        case resolved
        case recovered
        case pending
        case recoveryPct = "recovery_pct"
        case today
    }

    init(id: Int = 0, name: String = "", role: String = "", empCode: String? = nil, phone: String? = nil, email: String? = nil, assigned: Int = 0, resolved: Int = 0, recovered: Double = 0.0, pending: Double = 0.0, recoveryPct: Double = 0.0, today: MemberToday? = nil) {
        self.id = id
        self.name = name
        self.role = role
        self.empCode = empCode
        self.phone = phone
        self.email = email
        self.assigned = assigned
        self.resolved = resolved
        self.recovered = recovered
        self.pending = pending
        self.recoveryPct = recoveryPct
        self.today = today
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.name = c.d(.name, "")
        self.role = c.d(.role, "")
        self.empCode = c.opt(.empCode)
        self.phone = c.opt(.phone)
        self.email = c.opt(.email)
        self.assigned = c.d(.assigned, 0)
        self.resolved = c.d(.resolved, 0)
        self.recovered = c.d(.recovered, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.recoveryPct = c.d(.recoveryPct, 0.0)
        self.today = c.opt(.today)
    }
}

struct TeamOverview: Codable, Hashable {
    var lead: TeamLeadInfo?
    var members: [TeamMemberCard]
    var kpis: TeamKpis
    var leaderboard: [TeamMemberCard]

    enum CodingKeys: String, CodingKey {
        case lead
        case members
        case kpis
        case leaderboard
    }

    init(lead: TeamLeadInfo? = nil, members: [TeamMemberCard] = [], kpis: TeamKpis = TeamKpis(), leaderboard: [TeamMemberCard] = []) {
        self.lead = lead
        self.members = members
        self.kpis = kpis
        self.leaderboard = leaderboard
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.lead = c.opt(.lead)
        self.members = c.d(.members, [])
        self.kpis = c.d(.kpis, TeamKpis())
        self.leaderboard = c.d(.leaderboard, [])
    }
}

struct PingCreate: Codable, Hashable {
    var latitude: Double
    var longitude: Double
    var accuracy: Double?
    var speed: Double?
    var activeCaseId: Int?
    var deviceId: String?

    enum CodingKeys: String, CodingKey {
        case latitude
        case longitude
        case accuracy
        case speed
        case activeCaseId = "active_case_id"
        case deviceId = "device_id"
    }

    init(latitude: Double, longitude: Double, accuracy: Double? = nil, speed: Double? = nil, activeCaseId: Int? = nil, deviceId: String? = nil) {
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy = accuracy
        self.speed = speed
        self.activeCaseId = activeCaseId
        self.deviceId = deviceId
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.latitude = try c.req(.latitude)
        self.longitude = try c.req(.longitude)
        self.accuracy = c.opt(.accuracy)
        self.speed = c.opt(.speed)
        self.activeCaseId = c.opt(.activeCaseId)
        self.deviceId = c.opt(.deviceId)
    }
}

struct PingOut: Codable, Hashable, Identifiable {
    var id: Int
    var officerId: Int
    var latitude: Double
    var longitude: Double
    var accuracy: Double?
    var activeCaseId: Int?
    var createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case officerId = "officer_id"
        case latitude
        case longitude
        case accuracy
        case activeCaseId = "active_case_id"
        case createdAt = "created_at"
    }

    init(id: Int, officerId: Int, latitude: Double, longitude: Double, accuracy: Double? = nil, activeCaseId: Int? = nil, createdAt: String) {
        self.id = id
        self.officerId = officerId
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy = accuracy
        self.activeCaseId = activeCaseId
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.officerId = try c.req(.officerId)
        self.latitude = try c.req(.latitude)
        self.longitude = try c.req(.longitude)
        self.accuracy = c.opt(.accuracy)
        self.activeCaseId = c.opt(.activeCaseId)
        self.createdAt = try c.req(.createdAt)
    }
}

struct RoutePoint: Codable, Hashable {
    var lat: Double
    var lng: Double
    var at: String?

    enum CodingKeys: String, CodingKey {
        case lat
        case lng
        case at
    }

    init(lat: Double, lng: Double, at: String? = nil) {
        self.lat = lat
        self.lng = lng
        self.at = at
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.lat = try c.req(.lat)
        self.lng = try c.req(.lng)
        self.at = c.opt(.at)
    }
}

struct TodayRoute: Codable, Hashable {
    var count: Int
    var distanceKm: Double
    var points: [RoutePoint]

    enum CodingKeys: String, CodingKey {
        case count
        case distanceKm = "distance_km"
        case points
    }

    init(count: Int = 0, distanceKm: Double = 0.0, points: [RoutePoint] = []) {
        self.count = count
        self.distanceKm = distanceKm
        self.points = points
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.count = c.d(.count, 0)
        self.distanceKm = c.d(.distanceKm, 0.0)
        self.points = c.d(.points, [])
    }
}

struct OfficerLocation: Codable, Hashable {
    var officerId: Int
    var name: String
    var latitude: Double
    var longitude: Double
    var accuracy: Double?
    var activeCaseId: Int?
    var lastSeen: String

    enum CodingKeys: String, CodingKey {
        case officerId = "officer_id"
        case name
        case latitude
        case longitude
        case accuracy
        case activeCaseId = "active_case_id"
        case lastSeen = "last_seen"
    }

    init(officerId: Int, name: String, latitude: Double, longitude: Double, accuracy: Double? = nil, activeCaseId: Int? = nil, lastSeen: String) {
        self.officerId = officerId
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy = accuracy
        self.activeCaseId = activeCaseId
        self.lastSeen = lastSeen
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.officerId = try c.req(.officerId)
        self.name = try c.req(.name)
        self.latitude = try c.req(.latitude)
        self.longitude = try c.req(.longitude)
        self.accuracy = c.opt(.accuracy)
        self.activeCaseId = c.opt(.activeCaseId)
        self.lastSeen = try c.req(.lastSeen)
    }
}


// MARK: - Computed helpers (Kotlin class bodies)

extension User {
    var isFieldAgent: Bool { role == "fos" }
    var isTelecaller: Bool { role == "telecaller" }
    var isManager: Bool { role == "manager" }
    var isAdmin: Bool { role == "admin" }
    var isTeamLead: Bool { role == "teamlead" }
    var roleLabel: String {
        switch role {
        case "admin": return "Administrator"
        case "manager": return "Collections Manager"
        case "teamlead": return "Team Lead"
        case "fos": return "Field Agent"
        case "telecaller": return "Tele-calling Agent"
        case "headoffice": return "Head Office"
        case "backend": return "Back-office Official"
        case "hr": return "HR"
        case "it": return "IT"
        case "staff": return "Staff"
        default: return role.prefix(1).uppercased() + String(role.dropFirst())
        }
    }
}

extension Case {
    /// Working state for FOS/caller lists: fresh (untouched) → touched today → paid.
    var workState: String {
        if (paidStatus ?? "") == "PAID" || status == "paid" { return "paid" }
        if visitedToday == true || contactedToday == true || status == "in_progress" || status == "ptp" || status == "callback" {
            return "touched"
        }
        return "fresh"
    }
}

extension StaffOpt {
    var label: String { (name ?? "#\(id)") + (empCode.map { " (\($0))" } ?? "") }
}
