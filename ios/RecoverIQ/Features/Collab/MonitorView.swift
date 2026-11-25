import SwiftUI

// Port of MonitorScreen (ui/common/CollabScreens.kt) — live counters + activity feed, refreshed every 15 s.

struct MonitorView: View {
    init() {}

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("🖥️ Live Monitor  ·  updates every 15s")
                .font(.system(size: 17, weight: .bold)).foregroundColor(.TextDark)
            // Silent 15 s refresh via AsyncContent's reload (keeps the last data on screen, no loader flash).
            AsyncContent(load: { try await API.shared.monitorLive() }) { (d: [String: JSONValue], reload: @escaping () -> Void) in
                MonitorBody(d: d)
                    .task {
                        while !Task.isCancelled {
                            try? await Task.sleep(nanoseconds: 15_000_000_000)
                            if Task.isCancelled { break }
                            reload()
                        }
                    }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

private struct MonitorBody: View {
    let d: [String: JSONValue]

    var body: some View {
        let c: [String: JSONValue] = d["counters"].cm
        let feed: [JSONValue] = d["feed"].cl
        VStack(alignment: .leading, spacing: 4) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    CollabKpi("Online", String(c["online_now"].ci), .Good)
                    CollabKpi("Calls", String(c["calls"].ci))
                    CollabKpi("Visits", String(c["visits"].ci))
                    CollabKpi("Collected", inr(c["collected"].cd), .Good)
                }
                .padding(.vertical, 8)
            }
            ScrollView {
                LazyVStack(spacing: 4) {
                    if feed.isEmpty {
                        Text("No activity yet today.").font(.system(size: 12)).foregroundColor(.Muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    ForEach(0..<feed.count, id: \.self) { i in
                        MonitorFeedRow(f: feed[i].cm)
                    }
                }
                .padding(.bottom, 140)
            }
        }
    }
}

private struct MonitorFeedRow: View {
    let f: [String: JSONValue]

    var body: some View {
        HStack(spacing: 8) {
            Text(f["type"].cs == "call" ? "📞" : "📍")
            Text(f["who"].cs).fontWeight(.semibold).foregroundColor(.TextDark)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(f["detail"].cs).font(.system(size: 12)).foregroundColor(.BrandBlue)
            if f["amount"].cd > 0 {
                Text(inr(f["amount"].cd)).fontWeight(.bold).foregroundColor(.Good)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.GlassStroke, lineWidth: 1))
    }
}
