import Foundation

// Continuation of Models.swift (port of data/Models.kt). See Models.swift for the conventions.

struct StatusRow: Codable, Hashable {
    var status: String
    var count: Int

    enum CodingKeys: String, CodingKey {
        case status
        case count
    }

    init(status: String, count: Int) {
        self.status = status
        self.count = count
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.req(.status)
        self.count = try c.req(.count)
    }
}

struct PipelineRow: Codable, Hashable {
    var key: String
    var count: Int

    enum CodingKeys: String, CodingKey {
        case key
        case count
    }

    init(key: String, count: Int) {
        self.key = key
        self.count = count
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.key = try c.req(.key)
        self.count = try c.req(.count)
    }
}

struct AttPresence: Codable, Hashable {
    var state: String
    var platform: String?
    var lastSeen: String?
    var idleSeconds: Int

    enum CodingKeys: String, CodingKey {
        case state
        case platform
        case lastSeen = "last_seen"
        case idleSeconds = "idle_seconds"
    }

    init(state: String = "offline", platform: String? = nil, lastSeen: String? = nil, idleSeconds: Int = 0) {
        self.state = state
        self.platform = platform
        self.lastSeen = lastSeen
        self.idleSeconds = idleSeconds
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.state = c.d(.state, "offline")
        self.platform = c.opt(.platform)
        self.lastSeen = c.opt(.lastSeen)
        self.idleSeconds = c.d(.idleSeconds, 0)
    }
}

struct AttRow: Codable, Hashable {
    var userId: Int
    var name: String?
    var empCode: String?
    var role: String?
    var status: String
    var late: Bool
    var halfDayLeave: Bool
    var presentDays: Double
    var leaveDays: Double
    var absentDays: Double
    var checkInAt: String?
    var checkOutAt: String?
    var checkInLat: Double?
    var checkInLng: Double?
    var liveLat: Double?
    var liveLng: Double?
    var liveAt: String?
    var workedSeconds: Int
    var idleSeconds: Int
    var autoCheckout: Bool
    var calls: Int
    var visits: Int
    var collected: Double
    var showActivity: Bool
    var teamTotal: Bool
    var presence: AttPresence

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case name
        case empCode = "emp_code"
        case role
        case status
        case late
        case halfDayLeave = "half_day_leave"
        case presentDays = "present_days"
        case leaveDays = "leave_days"
        case absentDays = "absent_days"
        case checkInAt = "check_in_at"
        case checkOutAt = "check_out_at"
        case checkInLat = "check_in_lat"
        case checkInLng = "check_in_lng"
        case liveLat = "live_lat"
        case liveLng = "live_lng"
        case liveAt = "live_at"
        case workedSeconds = "worked_seconds"
        case idleSeconds = "idle_seconds"
        case autoCheckout = "auto_checkout"
        case calls
        case visits
        case collected
        case showActivity = "show_activity"
        case teamTotal = "team_total"
        case presence
    }

    init(userId: Int = 0, name: String? = nil, empCode: String? = nil, role: String? = nil, status: String = "absent", late: Bool = false, halfDayLeave: Bool = false, presentDays: Double = 0.0, leaveDays: Double = 0.0, absentDays: Double = 0.0, checkInAt: String? = nil, checkOutAt: String? = nil, checkInLat: Double? = nil, checkInLng: Double? = nil, liveLat: Double? = nil, liveLng: Double? = nil, liveAt: String? = nil, workedSeconds: Int = 0, idleSeconds: Int = 0, autoCheckout: Bool = false, calls: Int = 0, visits: Int = 0, collected: Double = 0.0, showActivity: Bool = false, teamTotal: Bool = false, presence: AttPresence = AttPresence()) {
        self.userId = userId
        self.name = name
        self.empCode = empCode
        self.role = role
        self.status = status
        self.late = late
        self.halfDayLeave = halfDayLeave
        self.presentDays = presentDays
        self.leaveDays = leaveDays
        self.absentDays = absentDays
        self.checkInAt = checkInAt
        self.checkOutAt = checkOutAt
        self.checkInLat = checkInLat
        self.checkInLng = checkInLng
        self.liveLat = liveLat
        self.liveLng = liveLng
        self.liveAt = liveAt
        self.workedSeconds = workedSeconds
        self.idleSeconds = idleSeconds
        self.autoCheckout = autoCheckout
        self.calls = calls
        self.visits = visits
        self.collected = collected
        self.showActivity = showActivity
        self.teamTotal = teamTotal
        self.presence = presence
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.userId = c.d(.userId, 0)
        self.name = c.opt(.name)
        self.empCode = c.opt(.empCode)
        self.role = c.opt(.role)
        self.status = c.d(.status, "absent")
        self.late = c.d(.late, false)
        self.halfDayLeave = c.d(.halfDayLeave, false)
        self.presentDays = c.d(.presentDays, 0.0)
        self.leaveDays = c.d(.leaveDays, 0.0)
        self.absentDays = c.d(.absentDays, 0.0)
        self.checkInAt = c.opt(.checkInAt)
        self.checkOutAt = c.opt(.checkOutAt)
        self.checkInLat = c.opt(.checkInLat)
        self.checkInLng = c.opt(.checkInLng)
        self.liveLat = c.opt(.liveLat)
        self.liveLng = c.opt(.liveLng)
        self.liveAt = c.opt(.liveAt)
        self.workedSeconds = c.d(.workedSeconds, 0)
        self.idleSeconds = c.d(.idleSeconds, 0)
        self.autoCheckout = c.d(.autoCheckout, false)
        self.calls = c.d(.calls, 0)
        self.visits = c.d(.visits, 0)
        self.collected = c.d(.collected, 0.0)
        self.showActivity = c.d(.showActivity, false)
        self.teamTotal = c.d(.teamTotal, false)
        self.presence = c.d(.presence, AttPresence())
    }
}

struct MeToday: Codable, Hashable {
    var tracked: Bool
    var needsCheckin: Bool
    var afterHours: Bool
    var field: Bool
    var shiftStart: String
    var shiftEnd: String
    var lateAfter: String
    var attendance: AttRow

    enum CodingKeys: String, CodingKey {
        case tracked
        case needsCheckin = "needs_checkin"
        case afterHours = "after_hours"
        case field
        case shiftStart = "shift_start"
        case shiftEnd = "shift_end"
        case lateAfter = "late_after"
        case attendance
    }

    init(tracked: Bool = false, needsCheckin: Bool = false, afterHours: Bool = false, field: Bool = false, shiftStart: String = "09:00", shiftEnd: String = "19:00", lateAfter: String = "10:00", attendance: AttRow = AttRow()) {
        self.tracked = tracked
        self.needsCheckin = needsCheckin
        self.afterHours = afterHours
        self.field = field
        self.shiftStart = shiftStart
        self.shiftEnd = shiftEnd
        self.lateAfter = lateAfter
        self.attendance = attendance
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.tracked = c.d(.tracked, false)
        self.needsCheckin = c.d(.needsCheckin, false)
        self.afterHours = c.d(.afterHours, false)
        self.field = c.d(.field, false)
        self.shiftStart = c.d(.shiftStart, "09:00")
        self.shiftEnd = c.d(.shiftEnd, "19:00")
        self.lateAfter = c.d(.lateAfter, "10:00")
        self.attendance = c.d(.attendance, AttRow())
    }
}

struct HeartbeatResp: Codable, Hashable {
    var promptOvertime: Bool
    var autoLogout: Bool
    var minutesToShiftEnd: Int?
    var checkedOut: Bool

    enum CodingKeys: String, CodingKey {
        case promptOvertime = "prompt_overtime"
        case autoLogout = "auto_logout"
        case minutesToShiftEnd = "minutes_to_shift_end"
        case checkedOut = "checked_out"
    }

    init(promptOvertime: Bool = false, autoLogout: Bool = false, minutesToShiftEnd: Int? = nil, checkedOut: Bool = false) {
        self.promptOvertime = promptOvertime
        self.autoLogout = autoLogout
        self.minutesToShiftEnd = minutesToShiftEnd
        self.checkedOut = checkedOut
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.promptOvertime = c.d(.promptOvertime, false)
        self.autoLogout = c.d(.autoLogout, false)
        self.minutesToShiftEnd = c.opt(.minutesToShiftEnd)
        self.checkedOut = c.d(.checkedOut, false)
    }
}

struct AttDaySummary: Codable, Hashable {
    var halfLeave: Int
    var present: Int
    var late: Int
    var absent: Int
    var leave: Int
    var online: Int
    var total: Int

    enum CodingKeys: String, CodingKey {
        case halfLeave = "half_leave"
        case present
        case late
        case absent
        case leave
        case online
        case total
    }

    init(halfLeave: Int = 0, present: Int = 0, late: Int = 0, absent: Int = 0, leave: Int = 0, online: Int = 0, total: Int = 0) {
        self.halfLeave = halfLeave
        self.present = present
        self.late = late
        self.absent = absent
        self.leave = leave
        self.online = online
        self.total = total
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.halfLeave = c.d(.halfLeave, 0)
        self.present = c.d(.present, 0)
        self.late = c.d(.late, 0)
        self.absent = c.d(.absent, 0)
        self.leave = c.d(.leave, 0)
        self.online = c.d(.online, 0)
        self.total = c.d(.total, 0)
    }
}

struct AttDay: Codable, Hashable {
    var date: String
    var rows: [AttRow]
    var summary: AttDaySummary
    var canDownload: Bool

    enum CodingKeys: String, CodingKey {
        case date
        case rows
        case summary
        case canDownload = "can_download"
    }

    init(date: String = "", rows: [AttRow] = [], summary: AttDaySummary = AttDaySummary(), canDownload: Bool = false) {
        self.date = date
        self.rows = rows
        self.summary = summary
        self.canDownload = canDownload
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.date = c.d(.date, "")
        self.rows = c.d(.rows, [])
        self.summary = c.d(.summary, AttDaySummary())
        self.canDownload = c.d(.canDownload, false)
    }
}

struct DispRow: Codable, Hashable {
    var disposition: String
    var count: Int

    enum CodingKeys: String, CodingKey {
        case disposition
        case count
    }

    init(disposition: String, count: Int) {
        self.disposition = disposition
        self.count = count
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.disposition = try c.req(.disposition)
        self.count = try c.req(.count)
    }
}

struct TrendPoint: Codable, Hashable {
    var date: String
    var collected: Double
    var visits: Int

    enum CodingKeys: String, CodingKey {
        case date
        case collected
        case visits
    }

    init(date: String, collected: Double, visits: Int) {
        self.date = date
        self.collected = collected
        self.visits = visits
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.date = try c.req(.date)
        self.collected = try c.req(.collected)
        self.visits = try c.req(.visits)
    }
}

struct LeaderRow: Codable, Hashable {
    var name: String
    var visits: Int
    var collected: Double

    enum CodingKeys: String, CodingKey {
        case name
        case visits
        case collected
    }

    init(name: String, visits: Int, collected: Double) {
        self.name = name
        self.visits = visits
        self.collected = collected
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.req(.name)
        self.visits = try c.req(.visits)
        self.collected = try c.req(.collected)
    }
}

struct DashboardResponse: Codable, Hashable {
    var kpis: DashboardKpis
    var byBank: [BankRow]
    var byStatus: [StatusRow]
    var pipeline: [PipelineRow]
    var byDisposition: [DispRow]
    var trend: [TrendPoint]
    var leaderboard: [LeaderRow]

    enum CodingKeys: String, CodingKey {
        case kpis
        case byBank = "by_bank"
        case byStatus = "by_status"
        case pipeline
        case byDisposition = "by_disposition"
        case trend
        case leaderboard = "fo_leaderboard"
    }

    init(kpis: DashboardKpis = DashboardKpis(), byBank: [BankRow] = [], byStatus: [StatusRow] = [], pipeline: [PipelineRow] = [], byDisposition: [DispRow] = [], trend: [TrendPoint] = [], leaderboard: [LeaderRow] = []) {
        self.kpis = kpis
        self.byBank = byBank
        self.byStatus = byStatus
        self.pipeline = pipeline
        self.byDisposition = byDisposition
        self.trend = trend
        self.leaderboard = leaderboard
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.kpis = c.d(.kpis, DashboardKpis())
        self.byBank = c.d(.byBank, [])
        self.byStatus = c.d(.byStatus, [])
        self.pipeline = c.d(.pipeline, [])
        self.byDisposition = c.d(.byDisposition, [])
        self.trend = c.d(.trend, [])
        self.leaderboard = c.d(.leaderboard, [])
    }
}

struct ActivityItem: Codable, Hashable {
    var type: String
    var at: String?
    var caseId: Int?
    var customer: String?
    var bank: String?
    var by: String?
    var amount: Double?
    var detail: String?
    var note: String?
    var lat: Double?
    var lng: Double?
    var photo: String?
    var offLocation: Bool?

    enum CodingKeys: String, CodingKey {
        case type
        case at
        case caseId = "case_id"
        case customer
        case bank
        case by
        case amount
        case detail
        case note
        case lat
        case lng
        case photo
        case offLocation = "off_location"
    }

    init(type: String, at: String? = nil, caseId: Int? = nil, customer: String? = nil, bank: String? = nil, by: String? = nil, amount: Double? = nil, detail: String? = nil, note: String? = nil, lat: Double? = nil, lng: Double? = nil, photo: String? = nil, offLocation: Bool? = nil) {
        self.type = type
        self.at = at
        self.caseId = caseId
        self.customer = customer
        self.bank = bank
        self.by = by
        self.amount = amount
        self.detail = detail
        self.note = note
        self.lat = lat
        self.lng = lng
        self.photo = photo
        self.offLocation = offLocation
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.type = try c.req(.type)
        self.at = c.opt(.at)
        self.caseId = c.opt(.caseId)
        self.customer = c.opt(.customer)
        self.bank = c.opt(.bank)
        self.by = c.opt(.by)
        self.amount = c.opt(.amount)
        self.detail = c.opt(.detail)
        self.note = c.opt(.note)
        self.lat = c.opt(.lat)
        self.lng = c.opt(.lng)
        self.photo = c.opt(.photo)
        self.offLocation = c.opt(.offLocation)
    }
}

struct Legal: Codable, Hashable, Identifiable {
    var id: Int
    var caseId: Int?
    var borrowerName: String?
    var bank: String?
    var matterType: String?
    var court: String?
    var caseNumber: String?
    var stage: String?
    var filedDate: String?
    var nextHearingDate: String?
    var status: String
    var amount: Double
    var notes: String?
    var branch: String?

    enum CodingKeys: String, CodingKey {
        case id
        case caseId = "case_id"
        case borrowerName = "borrower_name"
        case bank
        case matterType = "matter_type"
        case court
        case caseNumber = "case_number"
        case stage
        case filedDate = "filed_date"
        case nextHearingDate = "next_hearing_date"
        case status
        case amount
        case notes
        case branch
    }

    init(id: Int, caseId: Int? = nil, borrowerName: String? = nil, bank: String? = nil, matterType: String? = nil, court: String? = nil, caseNumber: String? = nil, stage: String? = nil, filedDate: String? = nil, nextHearingDate: String? = nil, status: String = "open", amount: Double = 0.0, notes: String? = nil, branch: String? = nil) {
        self.id = id
        self.caseId = caseId
        self.borrowerName = borrowerName
        self.bank = bank
        self.matterType = matterType
        self.court = court
        self.caseNumber = caseNumber
        self.stage = stage
        self.filedDate = filedDate
        self.nextHearingDate = nextHearingDate
        self.status = status
        self.amount = amount
        self.notes = notes
        self.branch = branch
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.caseId = c.opt(.caseId)
        self.borrowerName = c.opt(.borrowerName)
        self.bank = c.opt(.bank)
        self.matterType = c.opt(.matterType)
        self.court = c.opt(.court)
        self.caseNumber = c.opt(.caseNumber)
        self.stage = c.opt(.stage)
        self.filedDate = c.opt(.filedDate)
        self.nextHearingDate = c.opt(.nextHearingDate)
        self.status = c.d(.status, "open")
        self.amount = c.d(.amount, 0.0)
        self.notes = c.opt(.notes)
        self.branch = c.opt(.branch)
    }
}

struct LegalCreate: Codable, Hashable {
    var matterType: String
    var borrowerName: String?
    var bank: String?
    var court: String?
    var caseNumber: String?
    var stage: String?
    var nextHearingDate: String?
    var status: String
    var amount: Double
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case matterType = "matter_type"
        case borrowerName = "borrower_name"
        case bank
        case court
        case caseNumber = "case_number"
        case stage
        case nextHearingDate = "next_hearing_date"
        case status
        case amount
        case notes
    }

    init(matterType: String, borrowerName: String? = nil, bank: String? = nil, court: String? = nil, caseNumber: String? = nil, stage: String? = nil, nextHearingDate: String? = nil, status: String = "open", amount: Double = 0.0, notes: String? = nil) {
        self.matterType = matterType
        self.borrowerName = borrowerName
        self.bank = bank
        self.court = court
        self.caseNumber = caseNumber
        self.stage = stage
        self.nextHearingDate = nextHearingDate
        self.status = status
        self.amount = amount
        self.notes = notes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.matterType = try c.req(.matterType)
        self.borrowerName = c.opt(.borrowerName)
        self.bank = c.opt(.bank)
        self.court = c.opt(.court)
        self.caseNumber = c.opt(.caseNumber)
        self.stage = c.opt(.stage)
        self.nextHearingDate = c.opt(.nextHearingDate)
        self.status = c.d(.status, "open")
        self.amount = c.d(.amount, 0.0)
        self.notes = c.opt(.notes)
    }
}
