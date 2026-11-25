import Foundation

// Continuation of Models.swift (port of data/Models.kt). See Models.swift for the conventions.

struct LegalInsights: Codable, Hashable {
    var open: Int
    var hearingOverdue: Int
    var hearingToday: Int
    var hearingWeek: Int

    enum CodingKeys: String, CodingKey {
        case open
        case hearingOverdue = "hearing_overdue"
        case hearingToday = "hearing_today"
        case hearingWeek = "hearing_week"
    }

    init(open: Int = 0, hearingOverdue: Int = 0, hearingToday: Int = 0, hearingWeek: Int = 0) {
        self.open = open
        self.hearingOverdue = hearingOverdue
        self.hearingToday = hearingToday
        self.hearingWeek = hearingWeek
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.open = c.d(.open, 0)
        self.hearingOverdue = c.d(.hearingOverdue, 0)
        self.hearingToday = c.d(.hearingToday, 0)
        self.hearingWeek = c.d(.hearingWeek, 0)
    }
}

struct Leave: Codable, Hashable, Identifiable {
    var id: Int
    var userId: Int
    var leaveType: String?
    var startDate: String
    var endDate: String
    var days: Int
    var halfDay: Bool?
    var daysEffective: Double?
    var reason: String?
    var status: String
    var userName: String?
    var userBranch: String?
    var approverName: String?
    var decisionNote: String?
    var requestedStart: String?
    var requestedEnd: String?
    var requestedDays: Double?
    var partial: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case leaveType = "leave_type"
        case startDate = "start_date"
        case endDate = "end_date"
        case days
        case halfDay = "half_day"
        case daysEffective = "days_effective"
        case reason
        case status
        case userName = "user_name"
        case userBranch = "user_branch"
        case approverName = "approver_name"
        case decisionNote = "decision_note"
        case requestedStart = "requested_start"
        case requestedEnd = "requested_end"
        case requestedDays = "requested_days"
        case partial
    }

    init(id: Int, userId: Int, leaveType: String? = nil, startDate: String, endDate: String, days: Int, halfDay: Bool? = false, daysEffective: Double? = nil, reason: String? = nil, status: String, userName: String? = nil, userBranch: String? = nil, approverName: String? = nil, decisionNote: String? = nil, requestedStart: String? = nil, requestedEnd: String? = nil, requestedDays: Double? = nil, partial: Bool? = false) {
        self.id = id
        self.userId = userId
        self.leaveType = leaveType
        self.startDate = startDate
        self.endDate = endDate
        self.days = days
        self.halfDay = halfDay
        self.daysEffective = daysEffective
        self.reason = reason
        self.status = status
        self.userName = userName
        self.userBranch = userBranch
        self.approverName = approverName
        self.decisionNote = decisionNote
        self.requestedStart = requestedStart
        self.requestedEnd = requestedEnd
        self.requestedDays = requestedDays
        self.partial = partial
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.userId = try c.req(.userId)
        self.leaveType = c.opt(.leaveType)
        self.startDate = try c.req(.startDate)
        self.endDate = try c.req(.endDate)
        self.days = try c.req(.days)
        self.halfDay = c.optOr(.halfDay, false)
        self.daysEffective = c.opt(.daysEffective)
        self.reason = c.opt(.reason)
        self.status = try c.req(.status)
        self.userName = c.opt(.userName)
        self.userBranch = c.opt(.userBranch)
        self.approverName = c.opt(.approverName)
        self.decisionNote = c.opt(.decisionNote)
        self.requestedStart = c.opt(.requestedStart)
        self.requestedEnd = c.opt(.requestedEnd)
        self.requestedDays = c.opt(.requestedDays)
        self.partial = c.optOr(.partial, false)
    }
}

struct LeaveCreate: Codable, Hashable {
    var leaveType: String
    var startDate: String
    var endDate: String
    var reason: String?
    var halfDay: Bool

    enum CodingKeys: String, CodingKey {
        case leaveType = "leave_type"
        case startDate = "start_date"
        case endDate = "end_date"
        case reason
        case halfDay = "half_day"
    }

    init(leaveType: String, startDate: String, endDate: String, reason: String? = nil, halfDay: Bool = false) {
        self.leaveType = leaveType
        self.startDate = startDate
        self.endDate = endDate
        self.reason = reason
        self.halfDay = halfDay
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.leaveType = try c.req(.leaveType)
        self.startDate = try c.req(.startDate)
        self.endDate = try c.req(.endDate)
        self.reason = c.opt(.reason)
        self.halfDay = c.d(.halfDay, false)
    }
}

struct LeaveBalance: Codable, Hashable {
    var type: String
    var allowance: Int?
    var used: Double
    var pending: Double
    var remaining: Double?

    enum CodingKeys: String, CodingKey {
        case type
        case allowance
        case used
        case pending
        case remaining
    }

    init(type: String, allowance: Int? = nil, used: Double = 0.0, pending: Double = 0.0, remaining: Double? = nil) {
        self.type = type
        self.allowance = allowance
        self.used = used
        self.pending = pending
        self.remaining = remaining
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.type = try c.req(.type)
        self.allowance = c.opt(.allowance)
        self.used = c.d(.used, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.remaining = c.opt(.remaining)
    }
}

struct ChangeField: Codable, Hashable {
    var field: String
    var label: String
    var current: String?

    enum CodingKeys: String, CodingKey {
        case field
        case label
        case current
    }

    init(field: String, label: String, current: String? = nil) {
        self.field = field
        self.label = label
        self.current = current
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.field = try c.req(.field)
        self.label = try c.req(.label)
        self.current = c.opt(.current)
    }
}

struct ProfileChangeRequest: Codable, Hashable, Identifiable {
    var id: Int
    var userId: Int?
    var userName: String?
    var userCode: String?
    var userBranch: String?
    var field: String
    var fieldLabel: String?
    var oldValue: String?
    var newValue: String?
    var note: String?
    var status: String
    var reviewNote: String?
    var reviewerName: String?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case userName = "user_name"
        case userCode = "user_code"
        case userBranch = "user_branch"
        case field
        case fieldLabel = "field_label"
        case oldValue = "old_value"
        case newValue = "new_value"
        case note
        case status
        case reviewNote = "review_note"
        case reviewerName = "reviewer_name"
        case createdAt = "created_at"
    }

    init(id: Int, userId: Int? = nil, userName: String? = nil, userCode: String? = nil, userBranch: String? = nil, field: String, fieldLabel: String? = nil, oldValue: String? = nil, newValue: String? = nil, note: String? = nil, status: String, reviewNote: String? = nil, reviewerName: String? = nil, createdAt: String? = nil) {
        self.id = id
        self.userId = userId
        self.userName = userName
        self.userCode = userCode
        self.userBranch = userBranch
        self.field = field
        self.fieldLabel = fieldLabel
        self.oldValue = oldValue
        self.newValue = newValue
        self.note = note
        self.status = status
        self.reviewNote = reviewNote
        self.reviewerName = reviewerName
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.userId = c.opt(.userId)
        self.userName = c.opt(.userName)
        self.userCode = c.opt(.userCode)
        self.userBranch = c.opt(.userBranch)
        self.field = try c.req(.field)
        self.fieldLabel = c.opt(.fieldLabel)
        self.oldValue = c.opt(.oldValue)
        self.newValue = c.opt(.newValue)
        self.note = c.opt(.note)
        self.status = try c.req(.status)
        self.reviewNote = c.opt(.reviewNote)
        self.reviewerName = c.opt(.reviewerName)
        self.createdAt = c.opt(.createdAt)
    }
}

struct Device: Codable, Hashable, Identifiable {
    var id: Int
    var userId: Int
    var deviceId: String
    var label: String?
    var approved: Bool
    var userName: String?
    var userBranch: String?
    var userRole: String?
    var userCode: String?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case deviceId = "device_id"
        case label
        case approved
        case userName = "user_name"
        case userBranch = "user_branch"
        case userRole = "user_role"
        case userCode = "user_code"
    }

    init(id: Int, userId: Int, deviceId: String, label: String? = nil, approved: Bool = false, userName: String? = nil, userBranch: String? = nil, userRole: String? = nil, userCode: String? = nil) {
        self.id = id
        self.userId = userId
        self.deviceId = deviceId
        self.label = label
        self.approved = approved
        self.userName = userName
        self.userBranch = userBranch
        self.userRole = userRole
        self.userCode = userCode
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.userId = try c.req(.userId)
        self.deviceId = try c.req(.deviceId)
        self.label = c.opt(.label)
        self.approved = c.d(.approved, false)
        self.userName = c.opt(.userName)
        self.userBranch = c.opt(.userBranch)
        self.userRole = c.opt(.userRole)
        self.userCode = c.opt(.userCode)
    }
}

struct TwoFAStatus: Codable, Hashable {
    var enabled: Bool

    enum CodingKeys: String, CodingKey {
        case enabled
    }

    init(enabled: Bool = false) {
        self.enabled = enabled
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.enabled = c.d(.enabled, false)
    }
}

struct TwoFASetup: Codable, Hashable {
    var secret: String
    var otpauthUrl: String

    enum CodingKeys: String, CodingKey {
        case secret
        case otpauthUrl = "otpauth_url"
    }

    init(secret: String, otpauthUrl: String) {
        self.secret = secret
        self.otpauthUrl = otpauthUrl
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.secret = try c.req(.secret)
        self.otpauthUrl = try c.req(.otpauthUrl)
    }
}

struct OtpBody: Codable, Hashable {
    var otp: String

    enum CodingKeys: String, CodingKey {
        case otp
    }

    init(otp: String) {
        self.otp = otp
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.otp = try c.req(.otp)
    }
}

struct UserCreate: Codable, Hashable {
    var name: String
    var email: String
    var password: String
    var role: String
    var phone: String?
    var branch: String?
    var banks: [String]

    enum CodingKeys: String, CodingKey {
        case name
        case email
        case password
        case role
        case phone
        case branch
        case banks
    }

    init(name: String, email: String, password: String, role: String = "telecaller", phone: String? = nil, branch: String? = nil, banks: [String] = []) {
        self.name = name
        self.email = email
        self.password = password
        self.role = role
        self.phone = phone
        self.branch = branch
        self.banks = banks
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.req(.name)
        self.email = try c.req(.email)
        self.password = try c.req(.password)
        self.role = c.d(.role, "telecaller")
        self.phone = c.opt(.phone)
        self.branch = c.opt(.branch)
        self.banks = c.d(.banks, [])
    }
}

struct UserUpdate: Codable, Hashable {
    var name: String?
    var phone: String?
    var role: String?
    var branch: String?
    var isActive: Bool?
    var password: String?

    enum CodingKeys: String, CodingKey {
        case name
        case phone
        case role
        case branch
        case isActive = "is_active"
        case password
    }

    init(name: String? = nil, phone: String? = nil, role: String? = nil, branch: String? = nil, isActive: Bool? = nil, password: String? = nil) {
        self.name = name
        self.phone = phone
        self.role = role
        self.branch = branch
        self.isActive = isActive
        self.password = password
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = c.opt(.name)
        self.phone = c.opt(.phone)
        self.role = c.opt(.role)
        self.branch = c.opt(.branch)
        self.isActive = c.opt(.isActive)
        self.password = c.opt(.password)
    }
}

struct EmployeeProfile: Codable, Hashable, Identifiable {
    var id: Int
    var empCode: String?
    var hrRef: String?
    var name: String
    var email: String?
    var phone: String?
    var role: String
    var designation: String?
    var location: String?
    var branch: String?
    var gender: String?
    var dob: String?
    var joiningDate: String?
    var bloodGroup: String?
    var maritalStatus: String?
    var emergencyContact: String?
    var emergencyName: String?
    var emergencyRelation: String?
    var aadharNumber: String?
    var panNumber: String?
    var bankHolder: String?
    var bankAccount: String?
    var ifscCode: String?
    var bankName: String?
    var currentAddress: String?
    var photoUrl: String?
    var profileCompleted: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case empCode = "emp_code"
        case hrRef = "hr_ref"
        case name
        case email
        case phone
        case role
        case designation
        case location
        case branch
        case gender
        case dob
        case joiningDate = "joining_date"
        case bloodGroup = "blood_group"
        case maritalStatus = "marital_status"
        case emergencyContact = "emergency_contact"
        case emergencyName = "emergency_name"
        case emergencyRelation = "emergency_relation"
        case aadharNumber = "aadhar_number"
        case panNumber = "pan_number"
        case bankHolder = "bank_holder"
        case bankAccount = "bank_account"
        case ifscCode = "ifsc_code"
        case bankName = "bank_name"
        case currentAddress = "current_address"
        case photoUrl = "photo_url"
        case profileCompleted = "profile_completed"
    }

    init(id: Int = 0, empCode: String? = nil, hrRef: String? = nil, name: String = "", email: String? = nil, phone: String? = nil, role: String = "", designation: String? = nil, location: String? = nil, branch: String? = nil, gender: String? = nil, dob: String? = nil, joiningDate: String? = nil, bloodGroup: String? = nil, maritalStatus: String? = nil, emergencyContact: String? = nil, emergencyName: String? = nil, emergencyRelation: String? = nil, aadharNumber: String? = nil, panNumber: String? = nil, bankHolder: String? = nil, bankAccount: String? = nil, ifscCode: String? = nil, bankName: String? = nil, currentAddress: String? = nil, photoUrl: String? = nil, profileCompleted: Bool = false) {
        self.id = id
        self.empCode = empCode
        self.hrRef = hrRef
        self.name = name
        self.email = email
        self.phone = phone
        self.role = role
        self.designation = designation
        self.location = location
        self.branch = branch
        self.gender = gender
        self.dob = dob
        self.joiningDate = joiningDate
        self.bloodGroup = bloodGroup
        self.maritalStatus = maritalStatus
        self.emergencyContact = emergencyContact
        self.emergencyName = emergencyName
        self.emergencyRelation = emergencyRelation
        self.aadharNumber = aadharNumber
        self.panNumber = panNumber
        self.bankHolder = bankHolder
        self.bankAccount = bankAccount
        self.ifscCode = ifscCode
        self.bankName = bankName
        self.currentAddress = currentAddress
        self.photoUrl = photoUrl
        self.profileCompleted = profileCompleted
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.empCode = c.opt(.empCode)
        self.hrRef = c.opt(.hrRef)
        self.name = c.d(.name, "")
        self.email = c.opt(.email)
        self.phone = c.opt(.phone)
        self.role = c.d(.role, "")
        self.designation = c.opt(.designation)
        self.location = c.opt(.location)
        self.branch = c.opt(.branch)
        self.gender = c.opt(.gender)
        self.dob = c.opt(.dob)
        self.joiningDate = c.opt(.joiningDate)
        self.bloodGroup = c.opt(.bloodGroup)
        self.maritalStatus = c.opt(.maritalStatus)
        self.emergencyContact = c.opt(.emergencyContact)
        self.emergencyName = c.opt(.emergencyName)
        self.emergencyRelation = c.opt(.emergencyRelation)
        self.aadharNumber = c.opt(.aadharNumber)
        self.panNumber = c.opt(.panNumber)
        self.bankHolder = c.opt(.bankHolder)
        self.bankAccount = c.opt(.bankAccount)
        self.ifscCode = c.opt(.ifscCode)
        self.bankName = c.opt(.bankName)
        self.currentAddress = c.opt(.currentAddress)
        self.photoUrl = c.opt(.photoUrl)
        self.profileCompleted = c.d(.profileCompleted, false)
    }
}

struct ChangePasswordRequest: Codable, Hashable {
    var currentPassword: String
    var newPassword: String

    enum CodingKeys: String, CodingKey {
        case currentPassword = "current_password"
        case newPassword = "new_password"
    }

    init(currentPassword: String, newPassword: String) {
        self.currentPassword = currentPassword
        self.newPassword = newPassword
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.currentPassword = try c.req(.currentPassword)
        self.newPassword = try c.req(.newPassword)
    }
}
