import SwiftUI

// MisScreen.kt filter pieces: MisFilters, the "Filters" button with a count badge, the removable
// active-filter chips row and the Flipkart-style bottom sheet (branch / area / cycle / FOS / caller).

/// Everything currently selected in the filter sheet.
struct MisFilters: Equatable {
    var branches: Set<String> = []
    var area: String = ""
    var cycles: Set<String> = []
    var fos: Set<Int> = []
    var callers: Set<Int> = []

    var count: Int {
        let a: Int = area.trimmingCharacters(in: .whitespaces).isEmpty ? 0 : 1
        return branches.count + a + cycles.count + fos.count + callers.count
    }

    func csv(_ s: Set<Int>) -> String { s.sorted().map { String($0) }.joined(separator: ",") }
    func csvStr(_ s: Set<String>) -> String { s.sorted().joined(separator: ",") }

    /// Stable string for AsyncContent keys.
    var key: String {
        return "\(csvStr(branches))|\(area)|\(csvStr(cycles))|\(csv(fos))|\(csv(callers))"
    }
}

// MARK: - Filters button

struct MisFilterButton: View {
    let count: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "slider.horizontal.3").font(.system(size: 14, weight: .semibold))
                Text("Filters").font(.labelLarge)
                if count > 0 {
                    Text(String(count))
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.BrandBlue))
                }
            }
            .foregroundColor(.BrandBlue)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 10)
                .fill(count > 0 ? Color.BrandBlue.opacity(0.12) : Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.GlassStroke, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Active (removable) chips

struct MisActiveFilterChips: View {
    let filters: MisFilters
    let fopts: FilterOptions
    let onChange: (MisFilters) -> Void

    private func fosName(_ id: Int) -> String {
        return fopts.fos.first(where: { $0.id == id })?.name ?? "FOS #\(id)"
    }

    private func callerName(_ id: Int) -> String {
        return fopts.callers.first(where: { $0.id == id })?.name ?? "Caller #\(id)"
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if !filters.area.isEmpty {
                    MisRemChip(text: "Area: \(filters.area)") {
                        var f = filters; f.area = ""; onChange(f)
                    }
                }
                ForEach(filters.branches.sorted(), id: \.self) { b in
                    MisRemChip(text: "Branch: \(b)") {
                        var f = filters; f.branches.remove(b); onChange(f)
                    }
                }
                ForEach(filters.cycles.sorted(), id: \.self) { c in
                    MisRemChip(text: "Cyc \(c)") {
                        var f = filters; f.cycles.remove(c); onChange(f)
                    }
                }
                ForEach(filters.fos.sorted(), id: \.self) { id in
                    MisRemChip(text: fosName(id)) {
                        var f = filters; f.fos.remove(id); onChange(f)
                    }
                }
                ForEach(filters.callers.sorted(), id: \.self) { id in
                    MisRemChip(text: callerName(id)) {
                        var f = filters; f.callers.remove(id); onChange(f)
                    }
                }
            }
        }
    }
}

private struct MisRemChip: View {
    let text: String
    let onRemove: () -> Void

    var body: some View {
        Button(action: onRemove) {
            HStack(spacing: 4) {
                Text(text).font(.labelSmall).lineLimit(1)
                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
            }
            .foregroundColor(.BrandBlue)
            .padding(.leading, 10)
            .padding(.trailing, 6)
            .padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.BrandBlue.opacity(0.10)))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Bottom sheet

struct MisFilterSheet: View {
    let branchOpts: [String]
    let areas: [String]
    let fopts: FilterOptions
    let onApply: (MisFilters) -> Void
    let onDismiss: () -> Void

    @State private var draft: MisFilters

    init(branchOpts: [String], areas: [String], fopts: FilterOptions, initial: MisFilters,
         onApply: @escaping (MisFilters) -> Void, onDismiss: @escaping () -> Void) {
        self.branchOpts = branchOpts
        self.areas = areas
        self.fopts = fopts
        self.onApply = onApply
        self.onDismiss = onDismiss
        self._draft = State(initialValue: initial)
    }

    private var nothing: Bool {
        branchOpts.isEmpty && areas.isEmpty && fopts.cycles.isEmpty && fopts.fos.isEmpty && fopts.callers.isEmpty
    }

    private func people(_ list: [FilterPerson]) -> [(Int, String)] {
        return list.map { p in (p.id, p.name ?? "#\(p.id)") }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Filters").font(.titleLarge).fontWeight(.bold)
                Spacer()
                Button("Clear all") { draft = MisFilters() }
                    .foregroundColor(.BrandBlue)
            }
            .padding(.top, 16)
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    if !branchOpts.isEmpty {
                        MisMultiGroup(title: "Branch", options: branchOpts, selected: draft.branches) { draft.branches = $0 }
                    }
                    if !areas.isEmpty {
                        MisSingleGroup(title: "Area", options: areas, selected: draft.area) { draft.area = $0 }
                    }
                    if !fopts.cycles.isEmpty {
                        MisMultiGroup(title: "Cycle", options: fopts.cycles, selected: draft.cycles) { draft.cycles = $0 }
                    }
                    if !fopts.fos.isEmpty {
                        MisIntGroup(title: "FOS", options: people(fopts.fos), selected: draft.fos) { draft.fos = $0 }
                    }
                    if !fopts.callers.isEmpty {
                        MisIntGroup(title: "Caller", options: people(fopts.callers), selected: draft.callers) { draft.callers = $0 }
                    }
                    if nothing {
                        Text("No filters available for this portfolio.")
                            .font(.bodySmall).foregroundColor(.Muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: 10) {
                Button(action: onDismiss) {
                    Text("Cancel")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.BrandBlue)
                        .frame(maxWidth: .infinity, minHeight: 46)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.BrandBlue.opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)
                Button(action: { onApply(draft) }) {
                    Text(draft.count > 0 ? "Apply (\(draft.count))" : "Apply")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity, minHeight: 46)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.BrandBlue))
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 6)
            .padding(.bottom, 12)
        }
        .padding(.horizontal, 16)
    }
}

private struct MisGroupTitle: View {
    let title: String

    var body: some View {
        Text(title).font(.titleSmall).fontWeight(.semibold).padding(.top, 8)
    }
}

private struct MisMultiGroup: View {
    let title: String
    let options: [String]
    let selected: Set<String>
    let onChange: (Set<String>) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            MisGroupTitle(title: title)
            FlowLayout(spacing: 6, lineSpacing: 6) {
                ForEach(options, id: \.self) { opt in
                    Chip(label: opt, selected: selected.contains(opt)) {
                        var s = selected
                        if s.contains(opt) { s.remove(opt) } else { s.insert(opt) }
                        onChange(s)
                    }
                }
            }
        }
    }
}

private struct MisSingleGroup: View {
    let title: String
    let options: [String]
    let selected: String
    let onChange: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            MisGroupTitle(title: title)
            FlowLayout(spacing: 6, lineSpacing: 6) {
                ForEach(options, id: \.self) { opt in
                    Chip(label: opt, selected: opt == selected) {
                        onChange(opt == selected ? "" : opt)
                    }
                }
            }
        }
    }
}

private struct MisIntOption: Identifiable {
    let id: Int
    let name: String
}

private struct MisIntGroup: View {
    let title: String
    let options: [(Int, String)]
    let selected: Set<Int>
    let onChange: (Set<Int>) -> Void

    private var items: [MisIntOption] { options.map { MisIntOption(id: $0.0, name: $0.1) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            MisGroupTitle(title: title)
            FlowLayout(spacing: 6, lineSpacing: 6) {
                ForEach(items) { o in
                    Chip(label: o.name, selected: selected.contains(o.id)) {
                        var s = selected
                        if s.contains(o.id) { s.remove(o.id) } else { s.insert(o.id) }
                        onChange(s)
                    }
                }
            }
        }
    }
}
