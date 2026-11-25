import SwiftUI

// Port of ui/fos/MyVisitsScreen.kt — FOS self-service: every case visit I logged today
// (time, outcome, collection, photo).

struct MyVisitsView: View {
    var onOpenCase: (Int) -> Void

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    @State private var data: OfficerDayVisits? = nil
    @State private var loading: Bool = true
    @State private var error: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Today's Visits")
            if let d = data {
                HStack(spacing: 10) {
                    VisitStatBox(label: "Visits", value: String(d.count), valueColor: .TextDark)
                    VisitStatBox(label: "Collected", value: inr(d.collected), valueColor: .Good)
                }
                .padding(.bottom, 10)
            }
            stateContent
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task { await load() }
    }

    @ViewBuilder private var stateContent: some View {
        if loading {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let e = error {
            Text(e).foregroundColor(.Bad).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if (data?.visits ?? []).isEmpty {
            Text("No visits logged today yet.").foregroundColor(.MutedDim)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(data?.visits ?? []) { v in
                        VisitRowView(v: v, onOpenCase: onOpenCase)
                    }
                }
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        do {
            let d: OfficerDayVisits = try await API.shared.myVisitsForDay()
            data = d
        } catch {
            if error is CancellationError { return }
            let msg: String = error.localizedDescription
            self.error = msg.isEmpty ? "Could not load your visits" : msg
        }
        loading = false
    }
}

private struct VisitStatBox: View {
    let label: String
    let value: String
    let valueColor: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 12)).foregroundColor(.MutedDim)
            Text(value).font(.system(size: 20, weight: .bold)).foregroundColor(valueColor)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite))
        .shadow(color: Color.black.opacity(0.06), radius: 2, x: 0, y: 1)
    }
}

private struct VisitTag: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .medium))
            .foregroundColor(color)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 8).fill(color.opacity(0.12)))
    }
}

private struct VisitRowView: View {
    let v: DayVisit
    let onOpenCase: (Int) -> Void

    private var meta: String {
        let parts: [String] = [v.bank, v.product, v.account].compactMap { $0 }
        let s: String = parts.joined(separator: " · ")
        return s.trimmingCharacters(in: .whitespaces).isEmpty ? "—" : s
    }

    var body: some View {
        Button(action: { onOpenCase(v.caseId) }) {
            InfoCard {
                HStack(alignment: .center, spacing: 10) {
                    details.frame(maxWidth: .infinity, alignment: .leading)
                    photo
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Text(v.customer ?? "—").fontWeight(.semibold).foregroundColor(.TextDark)
                Text(v.time).font(.system(size: 12)).foregroundColor(.MutedDim)
            }
            Text(meta).font(.system(size: 12.5)).foregroundColor(.Muted)
            if let a = v.address, !a.trimmingCharacters(in: .whitespaces).isEmpty {
                Text(a).font(.system(size: 12)).foregroundColor(.MutedDim).lineLimit(2)
            }
            tags.padding(.top, 6)
            if let n = v.note, !n.trimmingCharacters(in: .whitespaces).isEmpty {
                Text(n).font(.system(size: 12.5)).foregroundColor(.Muted).padding(.top, 4)
            }
        }
    }

    private var tags: some View {
        FlowLayout(spacing: 6, lineSpacing: 6) {
            if let d = v.disposition, !d.trimmingCharacters(in: .whitespaces).isEmpty {
                VisitTag(text: d, color: .BrandBlue)
            }
            if v.paid && v.amount > 0 { VisitTag(text: "PAID " + inr(v.amount), color: .Good) }
            if let ns = v.normStab, !ns.trimmingCharacters(in: .whitespaces).isEmpty {
                VisitTag(text: ns, color: .Warn)
            }
            if v.personMoved { VisitTag(text: "MOVED", color: .Bad) }
            if v.offLocation { VisitTag(text: "OFF-LOCATION", color: .Warn) }
        }
    }

    @ViewBuilder private var photo: some View {
        if let url = Session.absoluteURL(v.photo) {
            AsyncImage(url: url) { phase in
                if let img = phase.image {
                    img.resizable().scaledToFill()
                } else {
                    Color.SurfaceVariant
                }
            }
            .frame(width: 64, height: 64)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .accessibilityLabel("Visit photo")
        }
    }
}
