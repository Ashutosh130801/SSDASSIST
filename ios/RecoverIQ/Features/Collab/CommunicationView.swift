import SwiftUI

// Port of ui/screens/CommunicationScreen.kt — message templates list (delete) + "New template" dialog.

struct CommunicationView: View {
    init() {}

    @State private var refresh: Int = 0
    @State private var showAdd: Bool = false

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            AsyncContent(key: AnyHashable(refresh), load: { try await API.shared.templates() }) { (templates: [Template], _: @escaping () -> Void) in
                if templates.isEmpty {
                    EmptyState("No message templates yet.")
                } else {
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            ForEach(templates) { t in
                                TemplateCard(t: t, onDelete: { delete(t.id) })
                            }
                        }
                        .padding(.top, 12)
                        .padding(.bottom, 90)
                    }
                }
            }
            .padding(.horizontal, 12)
            CollabExtendedFab("New template") { showAdd = true }
        }
        .sheet(isPresented: $showAdd) {
            AddTemplateSheet(onDismiss: { showAdd = false }, onConfirm: { body in create(body) })
        }
    }

    private func delete(_ id: Int) {
        Task {
            try? await API.shared.deleteTemplate(id: id)
            refresh += 1
        }
    }

    private func create(_ body: TemplateCreate) {
        Task {
            _ = try? await API.shared.createTemplate(body: body)
            showAdd = false
            refresh += 1
        }
    }
}

private struct TemplateCard: View {
    let t: Template
    let onDelete: () -> Void

    var body: some View {
        InfoCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(t.name).fontWeight(.semibold).foregroundColor(.TextDark)
                    Text(t.channel)
                        .font(.labelMedium).foregroundColor(.TextDark)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.StrokeSoft, lineWidth: 1))
                        .padding(.vertical, 4)
                    Text(t.body).font(.bodySmall).foregroundColor(.Muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Button(action: onDelete) {
                    Image(systemName: "trash.fill").foregroundColor(.Bad).frame(width: 36, height: 36)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Delete")
            }
        }
    }
}

private struct AddTemplateSheet: View {
    let onDismiss: () -> Void
    let onConfirm: (TemplateCreate) -> Void

    @State private var name: String = ""
    @State private var channel: String = "whatsapp"
    @State private var bodyText: String = ""

    private var canCreate: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && !bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    CollabField("Template name", text: $name)
                    Text("Channel").font(.labelSmall).foregroundColor(.Muted)
                    HStack(spacing: 6) {
                        Chip(label: "whatsapp", selected: channel == "whatsapp") { channel = "whatsapp" }
                        Chip(label: "sms", selected: channel == "sms") { channel = "sms" }
                    }
                    Text("Message body").font(.labelSmall).foregroundColor(.Muted)
                    TextEditor(text: $bodyText)
                        .frame(minHeight: 90)
                        .padding(6)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Color.CardWhite))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.StrokeSoft, lineWidth: 1))
                }
                .padding(16)
            }
            .navigationTitle("New template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onDismiss) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        onConfirm(TemplateCreate(name: name, channel: channel, body: bodyText))
                    }
                    .disabled(!canCreate)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
