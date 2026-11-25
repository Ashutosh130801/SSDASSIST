import SwiftUI

/// A button that opens a calendar and reports the picked date as an ISO "yyyy-MM-dd" string
/// (port of ui/common/DatePickerField.kt).
///
/// `DatePickerField(label: "PTP date", iso: ptpDate) { ptpDate = $0 }`
/// `DatePickerField(label: "From", iso: $from)`            // Binding variant
struct DatePickerField: View {
    let label: String
    let iso: String
    let onPick: (String) -> Void
    var minDate: Date? = nil
    var maxDate: Date? = nil

    @State private var open: Bool = false
    @State private var picked: Date = Date()

    init(label: String, iso: String, minDate: Date? = nil, maxDate: Date? = nil, onPick: @escaping (String) -> Void) {
        self.label = label
        self.iso = iso
        self.minDate = minDate
        self.maxDate = maxDate
        self.onPick = onPick
    }

    init(label: String, iso: Binding<String>, minDate: Date? = nil, maxDate: Date? = nil) {
        self.label = label
        self.iso = iso.wrappedValue
        self.minDate = minDate
        self.maxDate = maxDate
        self.onPick = { iso.wrappedValue = $0 }
    }

    private var title: String {
        let blank = iso.trimmingCharacters(in: .whitespaces).isEmpty
        return blank ? label : label + ": " + DateUtil.humanDate(iso)
    }

    var body: some View {
        Button(action: {
            picked = DateUtil.localDate(iso) ?? Date()
            open = true
        }) {
            HStack(spacing: 8) {
                Image(systemName: "calendar").font(.system(size: 15))
                Text(title).font(.system(size: 14, weight: .medium)).lineLimit(1)
                Spacer(minLength: 0)
            }
            .foregroundColor(.BrandBlue)
            .padding(.horizontal, 14).padding(.vertical, 11)
            .frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.CardWhite))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.StrokeSoft, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $open) { pickerSheet }
    }

    private var pickerSheet: some View {
        NavigationStack {
            VStack {
                datePicker
                    .datePickerStyle(.graphical)
                    .padding()
                Spacer()
            }
            .navigationTitle(label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { open = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") {
                        onPick(DateUtil.iso(picked))
                        open = false
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    @ViewBuilder private var datePicker: some View {
        if let lo = minDate, let hi = maxDate {
            DatePicker("", selection: $picked, in: lo...hi, displayedComponents: .date).labelsHidden()
        } else if let lo = minDate {
            DatePicker("", selection: $picked, in: lo..., displayedComponents: .date).labelsHidden()
        } else if let hi = maxDate {
            DatePicker("", selection: $picked, in: ...hi, displayedComponents: .date).labelsHidden()
        } else {
            DatePicker("", selection: $picked, displayedComponents: .date).labelsHidden()
        }
    }
}
