import SwiftUI

// Port of ChatThread (ui/common/CollabScreens.kt): bubbles (mine right / theirs left, sender name in the
// office thread), read receipts (✓✓ blue when read), reply composer, refreshed every 8 s.
// Refreshes silently (no loader flash) — Kotlin re-keys AsyncContent which keeps the old list visible.

struct ChatThreadView: View {
    let withId: Int?
    let office: Bool

    @State private var messages: [[String: JSONValue]] = []
    @State private var loaded: Bool = false
    @State private var error: String? = nil
    @State private var text: String = ""
    @State private var tick: Int = 0

    private struct LoadKey: Hashable {
        let withId: Int?
        let office: Bool
        let tick: Int
    }

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                WaColor.bg
                content
            }
            composer
        }
        .task(id: LoadKey(withId: withId, office: office, tick: tick)) { await load() }
        .task(id: LoadKey(withId: withId, office: office, tick: -1)) {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 8_000_000_000)
                if Task.isCancelled { break }
                tick += 1
            }
        }
        .onReceive(Realtime.shared.changed) { _ in tick += 1 }
    }

    @ViewBuilder private var content: some View {
        if !loaded {
            if let e = error {
                ErrorView(message: e, retry: { tick += 1 })
            } else {
                LogoLoader().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            messageList
        }
    }

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 5) {
                    if messages.isEmpty {
                        Text("No messages yet. Say hello 👋")
                            .font(.system(size: 12)).foregroundColor(WaColor.hint)
                            .padding(.horizontal, 12).padding(.vertical, 5)
                            .background(RoundedRectangle(cornerRadius: 8).fill(Color.white))
                            .frame(maxWidth: .infinity)
                    }
                    ForEach(0..<messages.count, id: \.self) { i in
                        ChatBubble(m: messages[i], office: office).id(i)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 10).padding(.vertical, 8)
            }
            .onAppear { proxy.scrollTo("bottom", anchor: .bottom) }
            .onChange(of: messages.count) { _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    private var composer: some View {
        HStack(spacing: 6) {
            TextField("Type a message", text: $text)
                .submitLabel(.send)
                .onSubmit { send() }
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 22).fill(Color.white))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.StrokeSoft, lineWidth: 1))
            Button(action: send) {
                Text("➤").font(.system(size: 17)).foregroundColor(.white)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(WaColor.header))
            }
            .buttonStyle(.plain)
        }
        .padding(8)
        .background(WaColor.bar)
    }

    private func load() async {
        do {
            let d: [String: JSONValue] = try await API.shared.chatThread(withId: withId, office: office)
            messages = d["messages"].cl.map { $0.cm }
            loaded = true
            error = nil
        } catch {
            if error is CancellationError { return }
            if !loaded { self.error = error.localizedDescription }
        }
    }

    private func send() {
        let b: String = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if b.isEmpty { return }
        text = ""
        var req: [String: JSONValue] = ["body": .string(b)]
        if office {
            req["office"] = .bool(true)
        } else {
            req["to_id"] = JSONValue(withId)
        }
        let payload: [String: JSONValue] = req
        Task {
            do {
                _ = try await API.shared.chatSend(body: payload)
                tick += 1
            } catch {
                // Kotlin swallows send errors
            }
        }
    }
}

private struct ChatBubble: View {
    let m: [String: JSONValue]
    let office: Bool

    var body: some View {
        let mine: Bool = m["mine"].cTrue
        HStack {
            if mine { Spacer(minLength: 70) }
            VStack(alignment: mine ? .trailing : .leading, spacing: 2) {
                if !mine && office {
                    Text(m["from"].cs).font(.system(size: 10.5, weight: .bold)).foregroundColor(WaColor.header)
                }
                Text(m["body"].cs).font(.system(size: 13)).foregroundColor(WaColor.ink)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                if mine {
                    Text("✓✓").font(.system(size: 10, weight: .bold))
                        .foregroundColor(m["read"].cTrue ? WaColor.tickRead : WaColor.tickSent)
                }
            }
            .padding(.horizontal, 9).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 8).fill(mine ? WaColor.outBubble : Color.white))
            if !mine { Spacer(minLength: 70) }
        }
    }
}
