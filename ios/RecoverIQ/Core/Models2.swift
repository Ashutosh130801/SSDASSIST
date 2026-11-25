import Foundation

// Continuation of Models.swift (port of data/Models.kt). See Models.swift for the conventions.

struct Case: Codable, Hashable, Identifiable {
    var id: Int
    var bank: String?
    var branch: String?
    var product: String?
    var segment: String?
    var accountNo: String?
    var cardNo: String?
    var customerName: String?
    var phone: String?
    var altPhone: String?
    var address: String?
    var address2: String?
    var address3: String?
    var newAddress: String?
    var newPhone: String?
    var newContactBy: String?
    var newContactAt: String?
    var pincode: String?
    var pincode2: String?
    var pincode3: String?
    var latitude: Double?
    var longitude: Double?
    var latitude2: Double?
    var longitude2: Double?
    var latitude3: Double?
    var longitude3: Double?
    var geoPrecision: String?
    var geoPrecision2: String?
    var geoPrecision3: String?
    var locationSource: String?
    var addressClean: String?
    var digipin: String?
    var bucket: String?
    var cycle: String?
    var month: String?
    var period: String?
    var totalOutstanding: Double
    var principalOutstanding: Double
    var minAmountDue: Double
    var fundingAmount: Double
    var receivedAmount: Double
    var pendingAmount: Double
    var enr: Double
    var normAmount: Double
    var stabAmount: Double
    var normStab: String?
    var isSettlementCase: Bool
    var remainingToNorm: Double?
    var remainingToStab: Double?
    var autoDebit: Bool
    var status: String?
    var paidStatus: String?
    var disposition: String?
    var remarks: String?
    var callerName: String?
    var fosName: String?
    var team: String?
    var teamLead: String?
    var cat: String?
    var assignedFosId: Int?
    var assignedCallerId: Int?
    var assignedFosName: String?
    var assignedFosPhone: String?
    var assignedFosCode: String?
    var assignedCallerName: String?
    var assignedCallerPhone: String?
    var assignedCallerCode: String?
    var followUpDate: String?
    var lastContactedAt: String?
    var visited: Bool?
    var visitedToday: Bool?
    var contactedToday: Bool?
    var escalated: Bool?
    var closed: Bool?
    var closeDate: String?
    var escPrevFosId: Int?
    var escPrevCallerId: Int?
    var jointFosId: Int?
    var jointFosName: String?
    var jointNote: String?
    var jointForMe: Bool?
    var reviewColor: String?
    var reviewNote: String?
    var propensity: Int?
    var flagged: Bool?
    var flagReason: String?

    enum CodingKeys: String, CodingKey {
        case id
        case bank
        case branch
        case product
        case segment
        case accountNo = "account_no"
        case cardNo = "card_no"
        case customerName = "customer_name"
        case phone
        case altPhone = "alt_phone"
        case address
        case address2
        case address3
        case newAddress = "new_address"
        case newPhone = "new_phone"
        case newContactBy = "new_contact_by"
        case newContactAt = "new_contact_at"
        case pincode
        case pincode2
        case pincode3
        case latitude
        case longitude
        case latitude2
        case longitude2
        case latitude3
        case longitude3
        case geoPrecision = "geo_precision"
        case geoPrecision2 = "geo_precision2"
        case geoPrecision3 = "geo_precision3"
        case locationSource = "location_source"
        case addressClean = "address_clean"
        case digipin
        case bucket
        case cycle
        case month
        case period
        case totalOutstanding = "total_outstanding"
        case principalOutstanding = "principal_outstanding"
        case minAmountDue = "min_amount_due"
        case fundingAmount = "funding_amount"
        case receivedAmount = "received_amount"
        case pendingAmount = "pending_amount"
        case enr
        case normAmount = "norm_amount"
        case stabAmount = "stab_amount"
        case normStab = "norm_stab"
        case isSettlementCase = "is_settlement_case"
        case remainingToNorm = "remaining_to_norm"
        case remainingToStab = "remaining_to_stab"
        case autoDebit = "auto_debit"
        case status
        case paidStatus = "paid_status"
        case disposition
        case remarks
        case callerName = "caller_name"
        case fosName = "fos_name"
        case team
        case teamLead = "team_lead"
        case cat
        case assignedFosId = "assigned_fos_id"
        case assignedCallerId = "assigned_caller_id"
        case assignedFosName = "assigned_fos_name"
        case assignedFosPhone = "assigned_fos_phone"
        case assignedFosCode = "assigned_fos_code"
        case assignedCallerName = "assigned_caller_name"
        case assignedCallerPhone = "assigned_caller_phone"
        case assignedCallerCode = "assigned_caller_code"
        case followUpDate = "follow_up_date"
        case lastContactedAt = "last_contacted_at"
        case visited
        case visitedToday = "visited_today"
        case contactedToday = "contacted_today"
        case escalated
        case closed
        case closeDate = "close_date"
        case escPrevFosId = "esc_prev_fos_id"
        case escPrevCallerId = "esc_prev_caller_id"
        case jointFosId = "joint_fos_id"
        case jointFosName = "joint_fos_name"
        case jointNote = "joint_note"
        case jointForMe = "joint_for_me"
        case reviewColor = "review_color"
        case reviewNote = "review_note"
        case propensity
        case flagged
        case flagReason = "flag_reason"
    }

    init(id: Int, bank: String? = nil, branch: String? = nil, product: String? = nil, segment: String? = nil, accountNo: String? = nil, cardNo: String? = nil, customerName: String? = nil, phone: String? = nil, altPhone: String? = nil, address: String? = nil, address2: String? = nil, address3: String? = nil, newAddress: String? = nil, newPhone: String? = nil, newContactBy: String? = nil, newContactAt: String? = nil, pincode: String? = nil, pincode2: String? = nil, pincode3: String? = nil, latitude: Double? = nil, longitude: Double? = nil, latitude2: Double? = nil, longitude2: Double? = nil, latitude3: Double? = nil, longitude3: Double? = nil, geoPrecision: String? = nil, geoPrecision2: String? = nil, geoPrecision3: String? = nil, locationSource: String? = nil, addressClean: String? = nil, digipin: String? = nil, bucket: String? = nil, cycle: String? = nil, month: String? = nil, period: String? = nil, totalOutstanding: Double = 0.0, principalOutstanding: Double = 0.0, minAmountDue: Double = 0.0, fundingAmount: Double = 0.0, receivedAmount: Double = 0.0, pendingAmount: Double = 0.0, enr: Double = 0.0, normAmount: Double = 0.0, stabAmount: Double = 0.0, normStab: String? = nil, isSettlementCase: Bool = false, remainingToNorm: Double? = nil, remainingToStab: Double? = nil, autoDebit: Bool = false, status: String? = nil, paidStatus: String? = nil, disposition: String? = nil, remarks: String? = nil, callerName: String? = nil, fosName: String? = nil, team: String? = nil, teamLead: String? = nil, cat: String? = nil, assignedFosId: Int? = nil, assignedCallerId: Int? = nil, assignedFosName: String? = nil, assignedFosPhone: String? = nil, assignedFosCode: String? = nil, assignedCallerName: String? = nil, assignedCallerPhone: String? = nil, assignedCallerCode: String? = nil, followUpDate: String? = nil, lastContactedAt: String? = nil, visited: Bool? = false, visitedToday: Bool? = false, contactedToday: Bool? = false, escalated: Bool? = false, closed: Bool? = false, closeDate: String? = nil, escPrevFosId: Int? = nil, escPrevCallerId: Int? = nil, jointFosId: Int? = nil, jointFosName: String? = nil, jointNote: String? = nil, jointForMe: Bool? = false, reviewColor: String? = nil, reviewNote: String? = nil, propensity: Int? = nil, flagged: Bool? = false, flagReason: String? = nil) {
        self.id = id
        self.bank = bank
        self.branch = branch
        self.product = product
        self.segment = segment
        self.accountNo = accountNo
        self.cardNo = cardNo
        self.customerName = customerName
        self.phone = phone
        self.altPhone = altPhone
        self.address = address
        self.address2 = address2
        self.address3 = address3
        self.newAddress = newAddress
        self.newPhone = newPhone
        self.newContactBy = newContactBy
        self.newContactAt = newContactAt
        self.pincode = pincode
        self.pincode2 = pincode2
        self.pincode3 = pincode3
        self.latitude = latitude
        self.longitude = longitude
        self.latitude2 = latitude2
        self.longitude2 = longitude2
        self.latitude3 = latitude3
        self.longitude3 = longitude3
        self.geoPrecision = geoPrecision
        self.geoPrecision2 = geoPrecision2
        self.geoPrecision3 = geoPrecision3
        self.locationSource = locationSource
        self.addressClean = addressClean
        self.digipin = digipin
        self.bucket = bucket
        self.cycle = cycle
        self.month = month
        self.period = period
        self.totalOutstanding = totalOutstanding
        self.principalOutstanding = principalOutstanding
        self.minAmountDue = minAmountDue
        self.fundingAmount = fundingAmount
        self.receivedAmount = receivedAmount
        self.pendingAmount = pendingAmount
        self.enr = enr
        self.normAmount = normAmount
        self.stabAmount = stabAmount
        self.normStab = normStab
        self.isSettlementCase = isSettlementCase
        self.remainingToNorm = remainingToNorm
        self.remainingToStab = remainingToStab
        self.autoDebit = autoDebit
        self.status = status
        self.paidStatus = paidStatus
        self.disposition = disposition
        self.remarks = remarks
        self.callerName = callerName
        self.fosName = fosName
        self.team = team
        self.teamLead = teamLead
        self.cat = cat
        self.assignedFosId = assignedFosId
        self.assignedCallerId = assignedCallerId
        self.assignedFosName = assignedFosName
        self.assignedFosPhone = assignedFosPhone
        self.assignedFosCode = assignedFosCode
        self.assignedCallerName = assignedCallerName
        self.assignedCallerPhone = assignedCallerPhone
        self.assignedCallerCode = assignedCallerCode
        self.followUpDate = followUpDate
        self.lastContactedAt = lastContactedAt
        self.visited = visited
        self.visitedToday = visitedToday
        self.contactedToday = contactedToday
        self.escalated = escalated
        self.closed = closed
        self.closeDate = closeDate
        self.escPrevFosId = escPrevFosId
        self.escPrevCallerId = escPrevCallerId
        self.jointFosId = jointFosId
        self.jointFosName = jointFosName
        self.jointNote = jointNote
        self.jointForMe = jointForMe
        self.reviewColor = reviewColor
        self.reviewNote = reviewNote
        self.propensity = propensity
        self.flagged = flagged
        self.flagReason = flagReason
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.bank = c.opt(.bank)
        self.branch = c.opt(.branch)
        self.product = c.opt(.product)
        self.segment = c.opt(.segment)
        self.accountNo = c.opt(.accountNo)
        self.cardNo = c.opt(.cardNo)
        self.customerName = c.opt(.customerName)
        self.phone = c.opt(.phone)
        self.altPhone = c.opt(.altPhone)
        self.address = c.opt(.address)
        self.address2 = c.opt(.address2)
        self.address3 = c.opt(.address3)
        self.newAddress = c.opt(.newAddress)
        self.newPhone = c.opt(.newPhone)
        self.newContactBy = c.opt(.newContactBy)
        self.newContactAt = c.opt(.newContactAt)
        self.pincode = c.opt(.pincode)
        self.pincode2 = c.opt(.pincode2)
        self.pincode3 = c.opt(.pincode3)
        self.latitude = c.opt(.latitude)
        self.longitude = c.opt(.longitude)
        self.latitude2 = c.opt(.latitude2)
        self.longitude2 = c.opt(.longitude2)
        self.latitude3 = c.opt(.latitude3)
        self.longitude3 = c.opt(.longitude3)
        self.geoPrecision = c.opt(.geoPrecision)
        self.geoPrecision2 = c.opt(.geoPrecision2)
        self.geoPrecision3 = c.opt(.geoPrecision3)
        self.locationSource = c.opt(.locationSource)
        self.addressClean = c.opt(.addressClean)
        self.digipin = c.opt(.digipin)
        self.bucket = c.opt(.bucket)
        self.cycle = c.opt(.cycle)
        self.month = c.opt(.month)
        self.period = c.opt(.period)
        self.totalOutstanding = c.d(.totalOutstanding, 0.0)
        self.principalOutstanding = c.d(.principalOutstanding, 0.0)
        self.minAmountDue = c.d(.minAmountDue, 0.0)
        self.fundingAmount = c.d(.fundingAmount, 0.0)
        self.receivedAmount = c.d(.receivedAmount, 0.0)
        self.pendingAmount = c.d(.pendingAmount, 0.0)
        self.enr = c.d(.enr, 0.0)
        self.normAmount = c.d(.normAmount, 0.0)
        self.stabAmount = c.d(.stabAmount, 0.0)
        self.normStab = c.opt(.normStab)
        self.isSettlementCase = c.d(.isSettlementCase, false)
        self.remainingToNorm = c.opt(.remainingToNorm)
        self.remainingToStab = c.opt(.remainingToStab)
        self.autoDebit = c.d(.autoDebit, false)
        self.status = c.opt(.status)
        self.paidStatus = c.opt(.paidStatus)
        self.disposition = c.opt(.disposition)
        self.remarks = c.opt(.remarks)
        self.callerName = c.opt(.callerName)
        self.fosName = c.opt(.fosName)
        self.team = c.opt(.team)
        self.teamLead = c.opt(.teamLead)
        self.cat = c.opt(.cat)
        self.assignedFosId = c.opt(.assignedFosId)
        self.assignedCallerId = c.opt(.assignedCallerId)
        self.assignedFosName = c.opt(.assignedFosName)
        self.assignedFosPhone = c.opt(.assignedFosPhone)
        self.assignedFosCode = c.opt(.assignedFosCode)
        self.assignedCallerName = c.opt(.assignedCallerName)
        self.assignedCallerPhone = c.opt(.assignedCallerPhone)
        self.assignedCallerCode = c.opt(.assignedCallerCode)
        self.followUpDate = c.opt(.followUpDate)
        self.lastContactedAt = c.opt(.lastContactedAt)
        self.visited = c.optOr(.visited, false)
        self.visitedToday = c.optOr(.visitedToday, false)
        self.contactedToday = c.optOr(.contactedToday, false)
        self.escalated = c.optOr(.escalated, false)
        self.closed = c.optOr(.closed, false)
        self.closeDate = c.opt(.closeDate)
        self.escPrevFosId = c.opt(.escPrevFosId)
        self.escPrevCallerId = c.opt(.escPrevCallerId)
        self.jointFosId = c.opt(.jointFosId)
        self.jointFosName = c.opt(.jointFosName)
        self.jointNote = c.opt(.jointNote)
        self.jointForMe = c.optOr(.jointForMe, false)
        self.reviewColor = c.opt(.reviewColor)
        self.reviewNote = c.opt(.reviewNote)
        self.propensity = c.opt(.propensity)
        self.flagged = c.optOr(.flagged, false)
        self.flagReason = c.opt(.flagReason)
    }
}

struct ReminderItem: Codable, Hashable {
    var caseId: Int
    var customer: String?
    var account: String?
    var bank: String?
    var phone: String?
    var ptpDate: String?
    var pending: Double
    var overdue: Bool

    enum CodingKeys: String, CodingKey {
        case caseId = "case_id"
        case customer
        case account
        case bank
        case phone
        case ptpDate = "ptp_date"
        case pending
        case overdue
    }

    init(caseId: Int, customer: String? = nil, account: String? = nil, bank: String? = nil, phone: String? = nil, ptpDate: String? = nil, pending: Double = 0.0, overdue: Bool = false) {
        self.caseId = caseId
        self.customer = customer
        self.account = account
        self.bank = bank
        self.phone = phone
        self.ptpDate = ptpDate
        self.pending = pending
        self.overdue = overdue
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.caseId = try c.req(.caseId)
        self.customer = c.opt(.customer)
        self.account = c.opt(.account)
        self.bank = c.opt(.bank)
        self.phone = c.opt(.phone)
        self.ptpDate = c.opt(.ptpDate)
        self.pending = c.d(.pending, 0.0)
        self.overdue = c.d(.overdue, false)
    }
}

struct RemindersResponse: Codable, Hashable {
    var date: String?
    var count: Int
    var overdue: Int
    var dueToday: Int
    var rows: [ReminderItem]

    enum CodingKeys: String, CodingKey {
        case date
        case count
        case overdue
        case dueToday = "due_today"
        case rows
    }

    init(date: String? = nil, count: Int = 0, overdue: Int = 0, dueToday: Int = 0, rows: [ReminderItem] = []) {
        self.date = date
        self.count = count
        self.overdue = overdue
        self.dueToday = dueToday
        self.rows = rows
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.date = c.opt(.date)
        self.count = c.d(.count, 0)
        self.overdue = c.d(.overdue, 0)
        self.dueToday = c.d(.dueToday, 0)
        self.rows = c.d(.rows, [])
    }
}

struct PaymentRequest: Codable, Hashable {
    var amount: Double
    var mode: String
    var note: String?
    var normStab: String?

    enum CodingKeys: String, CodingKey {
        case amount
        case mode
        case note
        case normStab = "norm_stab"
    }

    init(amount: Double, mode: String = "UPI", note: String? = nil, normStab: String? = nil) {
        self.amount = amount
        self.mode = mode
        self.note = note
        self.normStab = normStab
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.amount = try c.req(.amount)
        self.mode = c.d(.mode, "UPI")
        self.note = c.opt(.note)
        self.normStab = c.opt(.normStab)
    }
}

struct CaseUpdate: Codable, Hashable {
    var status: String?
    var disposition: String?
    var remarks: String?
    var followUpDate: String?

    enum CodingKeys: String, CodingKey {
        case status
        case disposition
        case remarks
        case followUpDate = "follow_up_date"
    }

    init(status: String? = nil, disposition: String? = nil, remarks: String? = nil, followUpDate: String? = nil) {
        self.status = status
        self.disposition = disposition
        self.remarks = remarks
        self.followUpDate = followUpDate
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = c.opt(.status)
        self.disposition = c.opt(.disposition)
        self.remarks = c.opt(.remarks)
        self.followUpDate = c.opt(.followUpDate)
    }
}

struct TimelineEvent: Codable, Hashable {
    var type: String
    var at: String?
    var by: String?
    var title: String
    var detail: String?
    var lat: Double?
    var lng: Double?
    var photo: String?
    var note: String?
    var amount: Double?
    var ptpDate: String?

    enum CodingKeys: String, CodingKey {
        case type
        case at
        case by
        case title
        case detail
        case lat
        case lng
        case photo
        case note
        case amount
        case ptpDate = "ptp_date"
    }

    init(type: String, at: String? = nil, by: String? = nil, title: String, detail: String? = nil, lat: Double? = nil, lng: Double? = nil, photo: String? = nil, note: String? = nil, amount: Double? = nil, ptpDate: String? = nil) {
        self.type = type
        self.at = at
        self.by = by
        self.title = title
        self.detail = detail
        self.lat = lat
        self.lng = lng
        self.photo = photo
        self.note = note
        self.amount = amount
        self.ptpDate = ptpDate
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.type = try c.req(.type)
        self.at = c.opt(.at)
        self.by = c.opt(.by)
        self.title = try c.req(.title)
        self.detail = c.opt(.detail)
        self.lat = c.opt(.lat)
        self.lng = c.opt(.lng)
        self.photo = c.opt(.photo)
        self.note = c.opt(.note)
        self.amount = c.opt(.amount)
        self.ptpDate = c.opt(.ptpDate)
    }
}

struct CallCreate: Codable, Hashable {
    var caseId: Int
    var disposition: String
    var ptpAmount: Double
    var ptpDate: String?
    var followUpDate: String?
    var paidAmount: Double
    var normStab: String?
    var note: String?

    enum CodingKeys: String, CodingKey {
        case caseId = "case_id"
        case disposition
        case ptpAmount = "ptp_amount"
        case ptpDate = "ptp_date"
        case followUpDate = "follow_up_date"
        case paidAmount = "paid_amount"
        case normStab = "norm_stab"
        case note
    }

    init(caseId: Int, disposition: String, ptpAmount: Double = 0.0, ptpDate: String? = nil, followUpDate: String? = nil, paidAmount: Double = 0.0, normStab: String? = nil, note: String? = nil) {
        self.caseId = caseId
        self.disposition = disposition
        self.ptpAmount = ptpAmount
        self.ptpDate = ptpDate
        self.followUpDate = followUpDate
        self.paidAmount = paidAmount
        self.normStab = normStab
        self.note = note
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.caseId = try c.req(.caseId)
        self.disposition = try c.req(.disposition)
        self.ptpAmount = c.d(.ptpAmount, 0.0)
        self.ptpDate = c.opt(.ptpDate)
        self.followUpDate = c.opt(.followUpDate)
        self.paidAmount = c.d(.paidAmount, 0.0)
        self.normStab = c.opt(.normStab)
        self.note = c.opt(.note)
    }
}

struct CallOut: Codable, Hashable, Identifiable {
    var id: Int
    var caseId: Int
    var callerId: Int
    var disposition: String
    var ptpAmount: Double
    var ptpDate: String?
    var note: String?
    var createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case caseId = "case_id"
        case callerId = "caller_id"
        case disposition
        case ptpAmount = "ptp_amount"
        case ptpDate = "ptp_date"
        case note
        case createdAt = "created_at"
    }

    init(id: Int, caseId: Int, callerId: Int, disposition: String, ptpAmount: Double = 0.0, ptpDate: String? = nil, note: String? = nil, createdAt: String) {
        self.id = id
        self.caseId = caseId
        self.callerId = callerId
        self.disposition = disposition
        self.ptpAmount = ptpAmount
        self.ptpDate = ptpDate
        self.note = note
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.caseId = try c.req(.caseId)
        self.callerId = try c.req(.callerId)
        self.disposition = try c.req(.disposition)
        self.ptpAmount = c.d(.ptpAmount, 0.0)
        self.ptpDate = c.opt(.ptpDate)
        self.note = c.opt(.note)
        self.createdAt = try c.req(.createdAt)
    }
}
