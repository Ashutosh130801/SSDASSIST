import SwiftUI
import UIKit

// Port of ui/ai/AiAssistScreen.kt — chat with the RecoverIQ assistant (POST api/ai → reply).
// Pushed by AppRoot (AppRoute.ai) so the navigation bar supplies the back button.
// Assistant replies are rendered with inline Markdown (bold / italics / code / links).

private struct AiMsg: Identifiable {
    let id: Int
    let text: String
    let fromUser: Bool
}

struct AiAssistView: View {
    init() {}

    @EnvironmentObject var app: AppState

    @State private var messages: [AiMsg] = []
    @State private var input: String = ""
    @State private var busy: Bool = false
    @State private var nextId: Int = 0

    private var canSend: Bool {
        !busy && !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            messageList
            inputBar
        }
        .appBackground()
        .navigationTitle("AI Assist")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { greetIfNeeded() }
    }

    // MARK: list

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(messages) { m in
                        AiBubble(msg: m).id(m.id)
                    }
                    if busy {
                        AiTypingBubble().id(-1)
                    }
                    Color.clear.frame(height: 1).id(-2)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: messages.count) { _ in
                withAnimation { proxy.scrollTo(-2, anchor: .bottom) }
            }
            .onChange(of: busy) { _ in
                withAnimation { proxy.scrollTo(-2, anchor: .bottom) }
            }
        }
    }

    // MARK: input

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Ask anything…", text: $input, axis: .vertical)
                .lineLimit(1...4)
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.StrokeSoft, lineWidth: 1))
            Button(action: send) {
                Image(systemName: "paperplane.fill")
                    .font(.system(size: 20))
                    .foregroundColor(canSend ? .BrandBlue : .MutedDim)
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .accessibilityLabel("Send")
        }
        .padding(10)
        .background(Color.CardWhite.shadow(color: Color.black.opacity(0.08), radius: 8, x: 0, y: -2))
    }

    // MARK: logic

    private func append(_ text: String, fromUser: Bool) {
        messages.append(AiMsg(id: nextId, text: text, fromUser: fromUser))
        nextId += 1
    }

    private func greetIfNeeded() {
        if !messages.isEmpty { return }
        let full: String = app.user?.name ?? ""
        let first: String = full.split(separator: " ").first.map { String($0) } ?? full
        append("Hi \(first) — I'm your RecoverIQ assistant. "
               + "Ask me about your cases, what to do next, or how anything in the app works.", fromUser: false)
    }

    private func send() {
        let q: String = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if q.isEmpty || busy { return }
        append(q, fromUser: true)
        input = ""
        busy = true
        Task {
            let reply: String
            do {
                reply = try await API.shared.aiAssist(prompt: q)
            } catch {
                reply = "I couldn't reach the assistant just now. Please try again."
            }
            append(reply, fromUser: false)
            busy = false
        }
    }
}

// MARK: - Bubbles

/// Inline-markdown rendering (keeps line breaks); falls back to plain text if parsing fails.
private func aiAttributed(_ s: String) -> AttributedString {
    let opts = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
    if let a = try? AttributedString(markdown: s, options: opts) { return a }
    return AttributedString(s)
}

private struct AiBubble: View {
    let msg: AiMsg

    var body: some View {
        HStack {
            if msg.fromUser { Spacer(minLength: 50) }
            bubble
            if !msg.fromUser { Spacer(minLength: 50) }
        }
    }

    @ViewBuilder private var textView: some View {
        if msg.fromUser {
            Text(msg.text)
        } else {
            Text(aiAttributed(msg.text))
        }
    }

    private var bubble: some View {
        textView
            .font(.bodyMedium)
            .foregroundColor(msg.fromUser ? .white : .TextDark)
            .tint(msg.fromUser ? .white : .BrandBlue)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 14).fill(msg.fromUser ? Color.BrandBlue : Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(msg.fromUser ? Color.clear : Color.GlassStroke, lineWidth: 1))
            .shadow(color: Color.black.opacity(msg.fromUser ? 0 : 0.06), radius: 3, x: 0, y: 1)
            .contextMenu {
                Button(action: { UIPasteboard.general.string = msg.text }) {
                    Label("Copy", systemImage: "doc.on.doc")
                }
            }
    }
}

private struct AiTypingBubble: View {
    var body: some View {
        HStack {
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.8)
                Text("Thinking…").font(.bodySmall).foregroundColor(.Muted)
            }
            .padding(14)
            .background(RoundedRectangle(cornerRadius: 14).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.GlassStroke, lineWidth: 1))
            Spacer()
        }
    }
}
