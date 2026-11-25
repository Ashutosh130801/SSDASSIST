import Foundation

// Continuation of Models.swift (port of data/Models.kt). See Models.swift for the conventions.

struct QueueResponse: Codable, Hashable {
    var due: [Case]
    var contactedToday: [Case]
    var upcoming: [Case]
    var counts: [String: Int]

    enum CodingKeys: String, CodingKey {
        case due
        case contactedToday = "contacted_today"
        case upcoming
        case counts
    }

    init(due: [Case] = [], contactedToday: [Case] = [], upcoming: [Case] = [], counts: [String: Int] = [:]) {
        self.due = due
        self.contactedToday = contactedToday
        self.upcoming = upcoming
        self.counts = counts
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.due = c.d(.due, [])
        self.contactedToday = c.d(.contactedToday, [])
        self.upcoming = c.d(.upcoming, [])
        self.counts = c.d(.counts, [:])
    }
}

struct CaseNote: Codable, Hashable {
    var by: String?
    var role: String?
    var source: String?
    var disposition: String?
    var text: String?
    var at: String?

    enum CodingKeys: String, CodingKey {
        case by
        case role
        case source
        case disposition
        case text
        case at = "when"
    }

    init(by: String? = nil, role: String? = nil, source: String? = nil, disposition: String? = nil, text: String? = nil, at: String? = nil) {
        self.by = by
        self.role = role
        self.source = source
        self.disposition = disposition
        self.text = text
        self.at = at
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.by = c.opt(.by)
        self.role = c.opt(.role)
        self.source = c.opt(.source)
        self.disposition = c.opt(.disposition)
        self.text = c.opt(.text)
        self.at = c.opt(.at)
    }
}

struct PtpRow: Codable, Hashable {
    var `case`: Case
    var ptpAmount: Double?
    var promisedDate: String?
    var bucket: String
    var notes: [CaseNote]

    enum CodingKeys: String, CodingKey {
        case `case`
        case ptpAmount = "ptp_amount"
        case promisedDate = "promised_date"
        case bucket
        case notes
    }

    init(`case`: Case, ptpAmount: Double? = nil, promisedDate: String? = nil, bucket: String, notes: [CaseNote] = []) {
        self.case = `case`
        self.ptpAmount = ptpAmount
        self.promisedDate = promisedDate
        self.bucket = bucket
        self.notes = notes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.case = try c.req(.case)
        self.ptpAmount = c.opt(.ptpAmount)
        self.promisedDate = c.opt(.promisedDate)
        self.bucket = try c.req(.bucket)
        self.notes = c.d(.notes, [])
    }
}

struct StaffOpt: Codable, Hashable, Identifiable {
    var id: Int
    var name: String?
    var empCode: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case empCode = "emp_code"
    }

    init(id: Int, name: String? = nil, empCode: String? = nil) {
        self.id = id
        self.name = name
        self.empCode = empCode
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.name = c.opt(.name)
        self.empCode = c.opt(.empCode)
    }
}

struct PtpResponse: Codable, Hashable {
    var rows: [PtpRow]
    var counts: [String: Int]
    var callers: [StaffOpt]
    var fos: [StaffOpt]

    enum CodingKeys: String, CodingKey {
        case rows
        case counts
        case callers
        case fos
    }

    init(rows: [PtpRow] = [], counts: [String: Int] = [:], callers: [StaffOpt] = [], fos: [StaffOpt] = []) {
        self.rows = rows
        self.counts = counts
        self.callers = callers
        self.fos = fos
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.rows = c.d(.rows, [])
        self.counts = c.d(.counts, [:])
        self.callers = c.d(.callers, [])
        self.fos = c.d(.fos, [])
    }
}

struct Template: Codable, Hashable, Identifiable {
    var id: Int
    var name: String
    var channel: String
    var body: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case channel
        case body
    }

    init(id: Int, name: String, channel: String, body: String) {
        self.id = id
        self.name = name
        self.channel = channel
        self.body = body
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.name = try c.req(.name)
        self.channel = try c.req(.channel)
        self.body = try c.req(.body)
    }
}

struct TemplateCreate: Codable, Hashable {
    var name: String
    var channel: String
    var body: String

    enum CodingKeys: String, CodingKey {
        case name
        case channel
        case body
    }

    init(name: String, channel: String = "whatsapp", body: String) {
        self.name = name
        self.channel = channel
        self.body = body
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.req(.name)
        self.channel = c.d(.channel, "whatsapp")
        self.body = try c.req(.body)
    }
}

struct CommLog: Codable, Hashable {
    var caseId: Int
    var channel: String
    var text: String?

    enum CodingKeys: String, CodingKey {
        case caseId = "case_id"
        case channel
        case text
    }

    init(caseId: Int, channel: String = "whatsapp", text: String? = nil) {
        self.caseId = caseId
        self.channel = channel
        self.text = text
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.caseId = try c.req(.caseId)
        self.channel = c.d(.channel, "whatsapp")
        self.text = c.opt(.text)
    }
}

struct VisitCreate: Codable, Hashable {
    var caseId: Int
    var latitude: Double?
    var longitude: Double?
    var gpsAccuracy: Double?
    var locationCorrect: Bool?
    var personMoved: Bool
    var paid: Bool
    var amountCollected: Double
    var disposition: String?
    var note: String?

    enum CodingKeys: String, CodingKey {
        case caseId = "case_id"
        case latitude
        case longitude
        case gpsAccuracy = "gps_accuracy"
        case locationCorrect = "location_correct"
        case personMoved = "person_moved"
        case paid
        case amountCollected = "amount_collected"
        case disposition
        case note
    }

    init(caseId: Int, latitude: Double? = nil, longitude: Double? = nil, gpsAccuracy: Double? = nil, locationCorrect: Bool? = nil, personMoved: Bool = false, paid: Bool = false, amountCollected: Double = 0.0, disposition: String? = nil, note: String? = nil) {
        self.caseId = caseId
        self.latitude = latitude
        self.longitude = longitude
        self.gpsAccuracy = gpsAccuracy
        self.locationCorrect = locationCorrect
        self.personMoved = personMoved
        self.paid = paid
        self.amountCollected = amountCollected
        self.disposition = disposition
        self.note = note
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.caseId = try c.req(.caseId)
        self.latitude = c.opt(.latitude)
        self.longitude = c.opt(.longitude)
        self.gpsAccuracy = c.opt(.gpsAccuracy)
        self.locationCorrect = c.opt(.locationCorrect)
        self.personMoved = c.d(.personMoved, false)
        self.paid = c.d(.paid, false)
        self.amountCollected = c.d(.amountCollected, 0.0)
        self.disposition = c.opt(.disposition)
        self.note = c.opt(.note)
    }
}

struct VisitOut: Codable, Hashable, Identifiable {
    var id: Int
    var caseId: Int
    var officerId: Int
    var latitude: Double?
    var longitude: Double?
    var photoPath: String?
    var locationCorrect: Bool?
    var personMoved: Bool?
    var paid: Bool?
    var amountCollected: Double
    var disposition: String?
    var note: String?
    var createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case caseId = "case_id"
        case officerId = "officer_id"
        case latitude
        case longitude
        case photoPath = "photo_path"
        case locationCorrect = "location_correct"
        case personMoved = "person_moved"
        case paid
        case amountCollected = "amount_collected"
        case disposition
        case note
        case createdAt = "created_at"
    }

    init(id: Int, caseId: Int, officerId: Int, latitude: Double? = nil, longitude: Double? = nil, photoPath: String? = nil, locationCorrect: Bool? = nil, personMoved: Bool? = nil, paid: Bool? = nil, amountCollected: Double = 0.0, disposition: String? = nil, note: String? = nil, createdAt: String) {
        self.id = id
        self.caseId = caseId
        self.officerId = officerId
        self.latitude = latitude
        self.longitude = longitude
        self.photoPath = photoPath
        self.locationCorrect = locationCorrect
        self.personMoved = personMoved
        self.paid = paid
        self.amountCollected = amountCollected
        self.disposition = disposition
        self.note = note
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.req(.id)
        self.caseId = try c.req(.caseId)
        self.officerId = try c.req(.officerId)
        self.latitude = c.opt(.latitude)
        self.longitude = c.opt(.longitude)
        self.photoPath = c.opt(.photoPath)
        self.locationCorrect = c.opt(.locationCorrect)
        self.personMoved = c.opt(.personMoved)
        self.paid = c.opt(.paid)
        self.amountCollected = c.d(.amountCollected, 0.0)
        self.disposition = c.opt(.disposition)
        self.note = c.opt(.note)
        self.createdAt = try c.req(.createdAt)
    }
}

struct OfficerDayVisits: Codable, Hashable {
    var officer: OfficerBrief?
    var date: String
    var count: Int
    var collected: Double
    var visits: [DayVisit]

    enum CodingKeys: String, CodingKey {
        case officer
        case date
        case count
        case collected
        case visits
    }

    init(officer: OfficerBrief? = nil, date: String = "", count: Int = 0, collected: Double = 0.0, visits: [DayVisit] = []) {
        self.officer = officer
        self.date = date
        self.count = count
        self.collected = collected
        self.visits = visits
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.officer = c.opt(.officer)
        self.date = c.d(.date, "")
        self.count = c.d(.count, 0)
        self.collected = c.d(.collected, 0.0)
        self.visits = c.d(.visits, [])
    }
}

struct OfficerBrief: Codable, Hashable, Identifiable {
    var id: Int
    var name: String?
    var branch: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case branch
    }

    init(id: Int = 0, name: String? = nil, branch: String? = nil) {
        self.id = id
        self.name = name
        self.branch = branch
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.name = c.opt(.name)
        self.branch = c.opt(.branch)
    }
}

struct DayVisit: Codable, Hashable, Identifiable {
    var id: Int
    var caseId: Int
    var time: String
    var lat: Double?
    var lng: Double?
    var customer: String?
    var account: String?
    var bank: String?
    var product: String?
    var phone: String?
    var address: String?
    var disposition: String?
    var paid: Bool
    var amount: Double
    var normStab: String?
    var personMoved: Bool
    var locationCorrect: Bool?
    var offLocation: Bool
    var distanceM: Double?
    var note: String?
    var photo: String?
    var paymentPhoto: String?

    enum CodingKeys: String, CodingKey {
        case id
        case caseId = "case_id"
        case time
        case lat
        case lng
        case customer
        case account
        case bank
        case product
        case phone
        case address
        case disposition
        case paid
        case amount
        case normStab = "norm_stab"
        case personMoved = "person_moved"
        case locationCorrect = "location_correct"
        case offLocation = "off_location"
        case distanceM = "distance_m"
        case note
        case photo
        case paymentPhoto = "payment_photo"
    }

    init(id: Int = 0, caseId: Int = 0, time: String = "", lat: Double? = nil, lng: Double? = nil, customer: String? = nil, account: String? = nil, bank: String? = nil, product: String? = nil, phone: String? = nil, address: String? = nil, disposition: String? = nil, paid: Bool = false, amount: Double = 0.0, normStab: String? = nil, personMoved: Bool = false, locationCorrect: Bool? = nil, offLocation: Bool = false, distanceM: Double? = nil, note: String? = nil, photo: String? = nil, paymentPhoto: String? = nil) {
        self.id = id
        self.caseId = caseId
        self.time = time
        self.lat = lat
        self.lng = lng
        self.customer = customer
        self.account = account
        self.bank = bank
        self.product = product
        self.phone = phone
        self.address = address
        self.disposition = disposition
        self.paid = paid
        self.amount = amount
        self.normStab = normStab
        self.personMoved = personMoved
        self.locationCorrect = locationCorrect
        self.offLocation = offLocation
        self.distanceM = distanceM
        self.note = note
        self.photo = photo
        self.paymentPhoto = paymentPhoto
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = c.d(.id, 0)
        self.caseId = c.d(.caseId, 0)
        self.time = c.d(.time, "")
        self.lat = c.opt(.lat)
        self.lng = c.opt(.lng)
        self.customer = c.opt(.customer)
        self.account = c.opt(.account)
        self.bank = c.opt(.bank)
        self.product = c.opt(.product)
        self.phone = c.opt(.phone)
        self.address = c.opt(.address)
        self.disposition = c.opt(.disposition)
        self.paid = c.d(.paid, false)
        self.amount = c.d(.amount, 0.0)
        self.normStab = c.opt(.normStab)
        self.personMoved = c.d(.personMoved, false)
        self.locationCorrect = c.opt(.locationCorrect)
        self.offLocation = c.d(.offLocation, false)
        self.distanceM = c.opt(.distanceM)
        self.note = c.opt(.note)
        self.photo = c.opt(.photo)
        self.paymentPhoto = c.opt(.paymentPhoto)
    }
}

struct AIRequest: Codable, Hashable {
    var prompt: String
    var context: String?

    enum CodingKeys: String, CodingKey {
        case prompt
        case context
    }

    init(prompt: String, context: String? = nil) {
        self.prompt = prompt
        self.context = context
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.prompt = try c.req(.prompt)
        self.context = c.opt(.context)
    }
}

struct AIResponse: Codable, Hashable {
    var reply: String

    enum CodingKeys: String, CodingKey {
        case reply
    }

    init(reply: String) {
        self.reply = reply
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.reply = try c.req(.reply)
    }
}

struct DashboardKpis: Codable, Hashable {
    var totalCases: Int
    var target: Double
    var received: Double
    var pending: Double
    var recoveryRate: Double
    var cashCollected: Double
    var paid: Int
    var unpaid: Int
    var partial: Int

    enum CodingKeys: String, CodingKey {
        case totalCases = "total_cases"
        case target
        case received
        case pending
        case recoveryRate = "recovery_rate"
        case cashCollected = "cash_collected"
        case paid
        case unpaid
        case partial
    }

    init(totalCases: Int = 0, target: Double = 0.0, received: Double = 0.0, pending: Double = 0.0, recoveryRate: Double = 0.0, cashCollected: Double = 0.0, paid: Int = 0, unpaid: Int = 0, partial: Int = 0) {
        self.totalCases = totalCases
        self.target = target
        self.received = received
        self.pending = pending
        self.recoveryRate = recoveryRate
        self.cashCollected = cashCollected
        self.paid = paid
        self.unpaid = unpaid
        self.partial = partial
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.totalCases = c.d(.totalCases, 0)
        self.target = c.d(.target, 0.0)
        self.received = c.d(.received, 0.0)
        self.pending = c.d(.pending, 0.0)
        self.recoveryRate = c.d(.recoveryRate, 0.0)
        self.cashCollected = c.d(.cashCollected, 0.0)
        self.paid = c.d(.paid, 0)
        self.unpaid = c.d(.unpaid, 0)
        self.partial = c.d(.partial, 0)
    }
}

struct BankRow: Codable, Hashable {
    var bank: String
    var cases: Int
    var received: Double
    var pending: Double

    enum CodingKeys: String, CodingKey {
        case bank
        case cases
        case received
        case pending
    }

    init(bank: String, cases: Int, received: Double, pending: Double) {
        self.bank = bank
        self.cases = cases
        self.received = received
        self.pending = pending
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.bank = try c.req(.bank)
        self.cases = try c.req(.cases)
        self.received = try c.req(.received)
        self.pending = try c.req(.pending)
    }
}
