import SwiftUI

/// Port of PayslipsScreen.kt — My Payslips: released payslips (PDF) + this year's income-tax summary
/// and the tax statement (Form 16 Part B) PDF. PDFs are downloaded then handed to the share sheet
/// (Quick Look / Files / Books / any PDF viewer).
struct PayslipsView: View {
    @State private var slips: [[String: JSONValue]]? = nil
    @State private var tax: [String: JSONValue]? = nil
    @State private var error: String? = nil
    @State private var busy: Int? = nil
    @State private var taxBusy: Bool = false

    init() {}

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                SectionTitle("My Payslips")
                if let e = error {
                    Text(e).foregroundColor(.Bad).font(.bodyMedium)
                }
                slipList
                taxSection
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 40)
        }
        .appBackground()
        .task { await load() }
    }

    // MARK: - Payslips

    @ViewBuilder private var slipList: some View {
        if let list = slips {
            if list.isEmpty {
                Text("No payslips released yet.").foregroundColor(.Muted).font(.bodyMedium)
            } else {
                ForEach(0..<list.count, id: \.self) { i in
                    slipCard(list[i])
                }
            }
        } else {
            HStack {
                Spacer()
                ProgressView()
                Spacer()
            }
            .padding(.vertical, 20)
        }
    }

    private func slipCard(_ p: [String: JSONValue]) -> some View {
        let id: Int = p.int("line_id") ?? 0
        let paid: Bool = p.str("pay_status") == "paid"
        let hold: Bool = p.bool("hold") == true
        let statusText: String = hold ? "On hold" : (paid ? "Paid \(p.str("paid_on") ?? "")" : "Processed")
        let statusColor: Color = hold ? .Bad : (paid ? .Good : .BrandBlue)
        let period: String = p.str("period") ?? "\(id)"
        return InfoCard(spacing: 4, padding: 14) {
            HStack {
                Text(p.str("label") ?? "").font(.titleMedium.weight(.bold)).foregroundColor(.TextDark)
                Spacer()
                Text(PayFmt.rupees(p["net"])).font(.titleMedium.weight(.bold)).foregroundColor(.Good)
            }
            Text("Gross \(PayFmt.rupees(p["gross"])) · Deductions \(PayFmt.rupees(p["deductions"]))")
                .font(.bodySmall).foregroundColor(.Muted)
            Text(statusText).font(.labelMedium).foregroundColor(statusColor)
            HRFilledButton(busy == id ? "Opening…" : "View / download PDF", enabled: busy == nil) {
                openSlip(id: id, period: period)
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Income tax

    @ViewBuilder private var taxSection: some View {
        if let t = tax, let proj = t["projection"]?.object {
            let fy: String = t.str("fy") ?? ""
            let annual: [String: JSONValue] = proj.obj("annual")
            SectionTitle("My income tax — FY \(fy)")
            InfoCard(spacing: 4, padding: 14) {
                Text("Regime: \(proj.str("regime") ?? "")").font(.bodyMedium.weight(.semibold)).foregroundColor(.TextDark)
                Text("Projected taxable income \(PayFmt.rupees(annual["taxable"]))").font(.bodySmall).foregroundColor(.TextDark)
                Text("Tax for the year \(PayFmt.rupees(annual["total"]))").font(.bodySmall).foregroundColor(.TextDark)
                Text("TDS so far \(PayFmt.rupees(proj["tds_so_far"])) · per month now \(PayFmt.rupees(proj["monthly_tds"]))")
                    .font(.bodySmall).foregroundColor(.Muted)
                HROutlinedButton(taxBusy ? "Opening…" : "Tax statement (PDF)", enabled: !taxBusy, fill: false) {
                    openForm16(fy: t.str("fy"))
                }
                .padding(.top, 4)
                Text("Change your regime or investment declarations on the web: My Payslips → My income tax.")
                    .font(.labelSmall).foregroundColor(.Muted)
            }
        }
    }

    // MARK: - Actions

    @MainActor private func load() async {
        do {
            slips = try await API.shared.myPayslips()
        } catch {
            self.error = error.localizedDescription
            slips = []
        }
        if let t = try? await API.shared.myTax() { tax = t }
    }

    private func openSlip(id: Int, period: String) {
        busy = id
        Task { @MainActor in
            do {
                let url: URL = try await API.shared.myPayslipPdf(id: id)
                HRUtil.shareRenamed(url, as: "Payslip_\(period).pdf")
                error = nil
            } catch {
                self.error = error.localizedDescription.isEmpty ? "Could not open the PDF" : error.localizedDescription
            }
            busy = nil
        }
    }

    private func openForm16(fy: String?) {
        taxBusy = true
        Task { @MainActor in
            do {
                let url: URL = try await API.shared.myForm16(fy: fy)
                HRUtil.shareRenamed(url, as: "Tax_Statement_FY\(fy ?? "").pdf")
                error = nil
            } catch {
                self.error = error.localizedDescription.isEmpty ? "Could not open the PDF" : error.localizedDescription
            }
            taxBusy = false
        }
    }
}

enum PayFmt {
    /// "₹" + "%,.2f" (Kotlin rupees()).
    static func rupees(_ v: JSONValue?) -> String {
        return "₹" + HRUtil.grouped(v?.double ?? 0.0, decimals: 2)
    }
}
