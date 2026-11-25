import SwiftUI

/// Port of ui/caller/CallerScreens.kt `CallQueueScreen` — Due now / Contacted / Upcoming segments.
struct CallQueueView: View {
    var onOpenCase: (Int) -> Void

    @State private var seg: String = "Due now"

    init(onOpenCase: @escaping (Int) -> Void) {
        self.onOpenCase = onOpenCase
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Call queue")
                .padding(.top, 12).padding(.leading, 4)
            AsyncContent(key: AnyHashable("queue"), live: true,
                         load: { try await API.shared.callQueue() }) { q, _ in
                CallQueueBody(q: q, seg: $seg, onOpenCase: onOpenCase)
            }
        }
        .padding(.horizontal, 12)
    }
}

private struct CallQueueBody: View {
    let q: QueueResponse
    @Binding var seg: String
    let onOpenCase: (Int) -> Void

    private var segments: [(String, [Case])] {
        return [("Due now", q.due), ("Contacted", q.contactedToday), ("Upcoming", q.upcoming)]
    }

    private var current: [Case] {
        return segments.first(where: { $0.0 == seg })?.1 ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(0..<segments.count, id: \.self) { i in
                        let label: String = segments[i].0
                        let n: Int = segments[i].1.count
                        Chip(label: "\(label) (\(n))", selected: seg == label) { seg = label }
                    }
                }
            }
            if current.isEmpty {
                EmptyState(text: "Nothing here right now.")
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(current) { c in
                            CaseCard(case: c, onClick: { onOpenCase(c.id) })
                        }
                    }
                    .padding(.top, 8).padding(.bottom, 16)
                }
            }
        }
    }
}
