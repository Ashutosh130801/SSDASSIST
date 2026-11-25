import Foundation

// Continuation of Models.swift (port of data/Models.kt). See Models.swift for the conventions.

struct NotificationItem: Codable, Hashable, Identifiable {
    var id: Int
    var caseId: Int?
    var type: String?
    var title: String?
    var body: String?
    var read: Bool
    var createdBy: String?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case caseId = "case_id"
        case type
        case title
        case body
        case read
        case createdBy = "created_by"
        case createdAt = "created_at"
    }

    init(id: Int = 0, caseId: Int? = nil, type: String? = nil, title: String? = nil, body: String? = nil, read: Bool = false, createdBy: String? = nil, createdAt: String? = nil) {
        self.id = id
        self.caseId = caseId
        self.type = type
        self.title = title
        self.body = body
        self.read = read
        self.createdBy = createdBy
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.caseId = c.opt(.caseId)
        self.type = c.opt(.type)
        self.title = c.opt(.title)
        self.body = c.opt(.body)
        self.read = c.d(.read, false)
        self.createdBy = c.opt(.createdBy)
        self.createdAt = c.opt(.createdAt)
    }
}

struct NotificationList: Codable, Hashable {
    var unread: Int
    var items: [NotificationItem]

    enum CodingKeys: String, CodingKey {
        case unread
        case items
    }

    init(unread: Int = 0, items: [NotificationItem] = []) {
        self.unread = unread
        self.items = items
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.unread = c.d(.unread, 0)
        self.items = c.d(.items, [])
    }
}

struct Trends: Codable, Hashable {
    var ftd: Double
    var mtd: Double
    var lmtd: Double
    var overall: Double

    enum CodingKeys: String, CodingKey {
        case ftd
        case mtd
        case lmtd
        case overall
    }

    init(ftd: Double = 0.0, mtd: Double = 0.0, lmtd: Double = 0.0, overall: Double = 0.0) {
        self.ftd = ftd
        self.mtd = mtd
        self.lmtd = lmtd
        self.overall = overall
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.ftd = c.d(.ftd, 0.0)
        self.mtd = c.d(.mtd, 0.0)
        self.lmtd = c.d(.lmtd, 0.0)
        self.overall = c.d(.overall, 0.0)
    }
}

struct EmployeeTrends: Codable, Hashable {
    var userId: Int
    var name: String?
    var empCode: String?
    var cases: Int
    var trends: Trends

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case name
        case empCode = "emp_code"
        case cases
        case trends
    }

    init(userId: Int = 0, name: String? = nil, empCode: String? = nil, cases: Int = 0, trends: Trends = Trends()) {
        self.userId = userId
        self.name = name
        self.empCode = empCode
        self.cases = cases
        self.trends = trends
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.userId = c.d(.userId, 0)
        self.name = c.opt(.name)
        self.empCode = c.opt(.empCode)
        self.cases = c.d(.cases, 0)
        self.trends = c.d(.trends, Trends())
    }
}

struct PortfolioBank: Codable, Hashable {
    var bank: String
    var logoDomain: String?
    var productCount: Int
    var count: Int
    var received: Double
    var pending: Double

    enum CodingKeys: String, CodingKey {
        case bank
        case logoDomain = "logo_domain"
        case productCount = "product_count"
        case count
        case received
        case pending
    }

    init(bank: String = "—", logoDomain: String? = nil, productCount: Int = 0, count: Int = 0, received: Double = 0.0, pending: Double = 0.0) {
        self.bank = bank
        self.logoDomain = logoDomain
        self.productCount = productCount
        self.count = count
        self.received = received
        self.pending = pending
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.bank = c.d(.bank, "—")
        self.logoDomain = c.opt(.logoDomain)
        self.productCount = c.d(.productCount, 0)
        self.count = c.d(.count, 0)
        self.received = c.d(.received, 0.0)
        self.pending = c.d(.pending, 0.0)
    }
}

struct BranchBucket: Codable, Hashable {
    var branch: String
    var count: Int
    var received: Double
    var pending: Double
    var paid: Int
    var unpaid: Int
    var countCurrent: Int
    var countNext: Int

    enum CodingKeys: String, CodingKey {
        case branch
        case count
        case received
        case pending
        case paid
        case unpaid
        case countCurrent = "count_current"
        case countNext = "count_next"
    }

    init(branch: String = "", count: Int = 0, received: Double = 0.0, pending: Double = 0.0, paid: Int = 0, unpaid: Int = 0, countCurrent: Int = 0, countNext: Int = 0) {
        self.branch = branch
        self.count = count
        self.received = received
        self.pending = pending
        self.paid = paid
        self.unpaid = unpaid
        self.countCurrent = countCurrent
        self.countNext = countNext
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.branch = c.d(.branch, "")
        self.count = c.d(.count, 0)
        self.received = c.d(.received, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.paid = c.d(.paid, 0)
        self.unpaid = c.d(.unpaid, 0)
        self.countCurrent = c.d(.countCurrent, 0)
        self.countNext = c.d(.countNext, 0)
    }
}

struct ProductSummary: Codable, Hashable {
    var bank: String
    var product: String
    var segment: String?
    var branch: String
    var branchSplit: Bool
    var count: Int
    var received: Double
    var pending: Double
    var paid: Int
    var unpaid: Int
    var countCurrent: Int
    var countNext: Int
    var branches: [BranchBucket]

    enum CodingKeys: String, CodingKey {
        case bank
        case product
        case segment
        case branch
        case branchSplit = "branch_split"
        case count
        case received
        case pending
        case paid
        case unpaid
        case countCurrent = "count_current"
        case countNext = "count_next"
        case branches
    }

    init(bank: String = "—", product: String = "—", segment: String? = nil, branch: String = "", branchSplit: Bool = false, count: Int = 0, received: Double = 0.0, pending: Double = 0.0, paid: Int = 0, unpaid: Int = 0, countCurrent: Int = 0, countNext: Int = 0, branches: [BranchBucket] = []) {
        self.bank = bank
        self.product = product
        self.segment = segment
        self.branch = branch
        self.branchSplit = branchSplit
        self.count = count
        self.received = received
        self.pending = pending
        self.paid = paid
        self.unpaid = unpaid
        self.countCurrent = countCurrent
        self.countNext = countNext
        self.branches = branches
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.bank = c.d(.bank, "—")
        self.product = c.d(.product, "—")
        self.segment = c.opt(.segment)
        self.branch = c.d(.branch, "")
        self.branchSplit = c.d(.branchSplit, false)
        self.count = c.d(.count, 0)
        self.received = c.d(.received, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.paid = c.d(.paid, 0)
        self.unpaid = c.d(.unpaid, 0)
        self.countCurrent = c.d(.countCurrent, 0)
        self.countNext = c.d(.countNext, 0)
        self.branches = c.d(.branches, [])
    }
}

struct FilterPerson: Codable, Hashable, Identifiable {
    var id: Int
    var name: String?
    var code: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case code
    }

    init(id: Int = 0, name: String? = nil, code: String? = nil) {
        self.id = id
        self.name = name
        self.code = code
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.name = c.opt(.name)
        self.code = c.opt(.code)
    }
}

struct FilterOptions: Codable, Hashable {
    var cycles: [String]
    var fos: [FilterPerson]
    var callers: [FilterPerson]

    enum CodingKeys: String, CodingKey {
        case cycles
        case fos
        case callers
    }

    init(cycles: [String] = [], fos: [FilterPerson] = [], callers: [FilterPerson] = []) {
        self.cycles = cycles
        self.fos = fos
        self.callers = callers
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.cycles = c.d(.cycles, [])
        self.fos = c.d(.fos, [])
        self.callers = c.d(.callers, [])
    }
}

struct PerfTotals: Codable, Hashable {
    var count: Int
    var paid: Int
    var unpaid: Int
    var enr: Double
    var paidEnr: Double
    var pending: Double
    var collected: Double
    var pos: Double
    var achievedPct: Double

    enum CodingKeys: String, CodingKey {
        case count
        case paid
        case unpaid
        case enr
        case paidEnr = "paid_enr"
        case pending
        case collected
        case pos
        case achievedPct = "achieved_pct"
    }

    init(count: Int = 0, paid: Int = 0, unpaid: Int = 0, enr: Double = 0.0, paidEnr: Double = 0.0, pending: Double = 0.0, collected: Double = 0.0, pos: Double = 0.0, achievedPct: Double = 0.0) {
        self.count = count
        self.paid = paid
        self.unpaid = unpaid
        self.enr = enr
        self.paidEnr = paidEnr
        self.pending = pending
        self.collected = collected
        self.pos = pos
        self.achievedPct = achievedPct
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.count = c.d(.count, 0)
        self.paid = c.d(.paid, 0)
        self.unpaid = c.d(.unpaid, 0)
        self.enr = c.d(.enr, 0.0)
        self.paidEnr = c.d(.paidEnr, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.collected = c.d(.collected, 0.0)
        self.pos = c.d(.pos, 0.0)
        self.achievedPct = c.d(.achievedPct, 0.0)
    }
}

struct PerfActivity: Codable, Hashable {
    var calls: Int
    var contacted: Int
    var visits: Int
    var visitsPaid: Int
    var visited: Int
    var collected: Double

    enum CodingKeys: String, CodingKey {
        case calls
        case contacted
        case visits
        case visitsPaid = "visits_paid"
        case visited
        case collected
    }

    init(calls: Int = 0, contacted: Int = 0, visits: Int = 0, visitsPaid: Int = 0, visited: Int = 0, collected: Double = 0.0) {
        self.calls = calls
        self.contacted = contacted
        self.visits = visits
        self.visitsPaid = visitsPaid
        self.visited = visited
        self.collected = collected
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.calls = c.d(.calls, 0)
        self.contacted = c.d(.contacted, 0)
        self.visits = c.d(.visits, 0)
        self.visitsPaid = c.d(.visitsPaid, 0)
        self.visited = c.d(.visited, 0)
        self.collected = c.d(.collected, 0.0)
    }
}

struct PerfLeaderRow: Codable, Hashable {
    var rank: Int
    var name: String
    var you: Bool
    var count: Int
    var enr: Double
    var paidEnr: Double
    var achievedPct: Double
    var collected: Double

    enum CodingKeys: String, CodingKey {
        case rank
        case name
        case you
        case count
        case enr
        case paidEnr = "paid_enr"
        case achievedPct = "achieved_pct"
        case collected
    }

    init(rank: Int = 0, name: String = "", you: Bool = false, count: Int = 0, enr: Double = 0.0, paidEnr: Double = 0.0, achievedPct: Double = 0.0, collected: Double = 0.0) {
        self.rank = rank
        self.name = name
        self.you = you
        self.count = count
        self.enr = enr
        self.paidEnr = paidEnr
        self.achievedPct = achievedPct
        self.collected = collected
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.rank = c.d(.rank, 0)
        self.name = c.d(.name, "")
        self.you = c.d(.you, false)
        self.count = c.d(.count, 0)
        self.enr = c.d(.enr, 0.0)
        self.paidEnr = c.d(.paidEnr, 0.0)
        self.achievedPct = c.d(.achievedPct, 0.0)
        self.collected = c.d(.collected, 0.0)
    }
}

struct PerfPortfolio: Codable, Hashable {
    var label: String
    var count: Int
    var paid: Int
    var unpaid: Int
    var enr: Double
    var paidEnr: Double
    var pending: Double
    var pos: Double
    var collected: Double
    var achievedPct: Double
    var targetPct: Double
    var toTargetPct: Double
    var rank: Int?
    var fieldSize: Int
    var activity: PerfActivity
    var trends: Trends
    var leaderboard: [PerfLeaderRow]

    enum CodingKeys: String, CodingKey {
        case label
        case count
        case paid
        case unpaid
        case enr
        case paidEnr = "paid_enr"
        case pending
        case pos
        case collected
        case achievedPct = "achieved_pct"
        case targetPct = "target_pct"
        case toTargetPct = "to_target_pct"
        case rank
        case fieldSize = "field_size"
        case activity
        case trends
        case leaderboard
    }

    init(label: String = "", count: Int = 0, paid: Int = 0, unpaid: Int = 0, enr: Double = 0.0, paidEnr: Double = 0.0, pending: Double = 0.0, pos: Double = 0.0, collected: Double = 0.0, achievedPct: Double = 0.0, targetPct: Double = 0.0, toTargetPct: Double = 0.0, rank: Int? = nil, fieldSize: Int = 0, activity: PerfActivity = PerfActivity(), trends: Trends = Trends(), leaderboard: [PerfLeaderRow] = []) {
        self.label = label
        self.count = count
        self.paid = paid
        self.unpaid = unpaid
        self.enr = enr
        self.paidEnr = paidEnr
        self.pending = pending
        self.pos = pos
        self.collected = collected
        self.achievedPct = achievedPct
        self.targetPct = targetPct
        self.toTargetPct = toTargetPct
        self.rank = rank
        self.fieldSize = fieldSize
        self.activity = activity
        self.trends = trends
        self.leaderboard = leaderboard
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.label = c.d(.label, "")
        self.count = c.d(.count, 0)
        self.paid = c.d(.paid, 0)
        self.unpaid = c.d(.unpaid, 0)
        self.enr = c.d(.enr, 0.0)
        self.paidEnr = c.d(.paidEnr, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.pos = c.d(.pos, 0.0)
        self.collected = c.d(.collected, 0.0)
        self.achievedPct = c.d(.achievedPct, 0.0)
        self.targetPct = c.d(.targetPct, 0.0)
        self.toTargetPct = c.d(.toTargetPct, 0.0)
        self.rank = c.opt(.rank)
        self.fieldSize = c.d(.fieldSize, 0)
        self.activity = c.d(.activity, PerfActivity())
        self.trends = c.d(.trends, Trends())
        self.leaderboard = c.d(.leaderboard, [])
    }
}

struct Performance: Codable, Hashable {
    var name: String?
    var empCode: String?
    var asFos: Bool
    var totals: PerfTotals
    var activity: PerfActivity
    var trends: Trends
    var portfolios: [PerfPortfolio]

    enum CodingKeys: String, CodingKey {
        case name
        case empCode = "emp_code"
        case asFos = "as_fos"
        case totals
        case activity
        case trends
        case portfolios
    }

    init(name: String? = nil, empCode: String? = nil, asFos: Bool = false, totals: PerfTotals = PerfTotals(), activity: PerfActivity = PerfActivity(), trends: Trends = Trends(), portfolios: [PerfPortfolio] = []) {
        self.name = name
        self.empCode = empCode
        self.asFos = asFos
        self.totals = totals
        self.activity = activity
        self.trends = trends
        self.portfolios = portfolios
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = c.opt(.name)
        self.empCode = c.opt(.empCode)
        self.asFos = c.d(.asFos, false)
        self.totals = c.d(.totals, PerfTotals())
        self.activity = c.d(.activity, PerfActivity())
        self.trends = c.d(.trends, Trends())
        self.portfolios = c.d(.portfolios, [])
    }
}
