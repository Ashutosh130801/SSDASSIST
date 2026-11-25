import SwiftUI
import UIKit
import CoreLocation

/// Which picker is on screen.
private enum VisitPickerTarget: String, Identifiable {
    case visitCamera
    case paymentCamera
    case paymentGallery
    var id: String { rawValue }
}

private let GOOD_ACC_M: Double = 30.0   // wait for at least this accuracy before the photo

/// "Log field visit" — port of LogVisitDialog in ui/detail/VisitDialog.kt.
///  * which of the customer's addresses is being visited (1 / 2 / 3 / new)
///  * live, hardened GPS while the form is open (accuracy gate ±30 m, mock detection, fix age,
///    reverse-geocoded address / PIN / city, re-looked-up when he moves > 50 m)
///  * in-app camera photo with the GPS / time / address stamp + map thumbnail burned in
///    (GPS frozen the moment the photo is taken — that is the visit's location)
///  * outcome, payment collected + amount, STAB / NORM (credit card), PTP date, person moved, note
///  * optional payment screenshot (gallery / camera)
///  * multipart submit via API.createVisit(...); the real server reason is shown on failure and the
///    entry is kept; on success the summary + photos are shared (WhatsApp / self).
struct LogVisitSheet: View {
    let `case`: Case
    let onDone: () -> Void

    @EnvironmentObject var app: AppState

    private let addresses: [VisitAddress]
    private static let dispositions: [String] = ["Met customer", "Not available", "Paid", "Wrong address", "Person moved", "PTP"]

    @State private var slot: String
    @State private var disp: String = "Met customer"
    @State private var paid: Bool = false
    @State private var moved: Bool = false
    @State private var amount: String = ""
    @State private var normStab: String = "STAB"
    @State private var ptpDate: String = ""
    @State private var note: String = ""

    @State private var photo: UIImage? = nil
    @State private var stamping: Bool = false
    @State private var paymentPhoto: UIImage? = nil
    @State private var picker: VisitPickerTarget? = nil

    @State private var lastFix: GPSFix? = nil
    @State private var geocodedAt: GPSFix? = nil
    @State private var address: String? = nil
    @State private var gpsPincode: String? = nil
    @State private var gpsCity: String? = nil
    @State private var mock: Bool = false
    @State private var gpsError: String? = nil
    @State private var shot: GPSFix? = nil            // GPS frozen at photo time
    @State private var shotAge: Double? = nil         // its age at that moment
    @State private var override: Bool = false         // take photo despite weak GPS

    @State private var submitting: Bool = false
    @State private var submitError: String? = nil
    @State private var saved: VisitDraft? = nil

    init(case c: Case, onDone: @escaping () -> Void) {
        self.case = c
        self.onDone = onDone
        let list: [VisitAddress] = CaseText.visitAddresses(c)
        self.addresses = list
        self._slot = State(initialValue: list.first?.key ?? "1")
    }

    private var isCreditCard: Bool { self.case.segment == "Credit Card" }
    private var chosen: VisitAddress? { addresses.first(where: { $0.key == slot }) }
    private var acc: Double? { lastFix?.accuracy }
    private var goodFix: Bool { lastFix != nil && (acc ?? 999.0) <= GOOD_ACC_M }
    private var caseLabel: String {
        var s: String = "Case #" + String(self.case.id)
        if let n = self.case.customerName { s += " • " + n }
        return s
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let d = saved {
                    successView(d).padding(16)
                } else {
                    form.padding(16)
                }
            }
            .navigationTitle("Log field visit")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbar }
        }
        .interactiveDismissDisabled(submitting || stamping)
        .task { await gpsLoop() }
        .fullScreenCover(item: $picker) { target in
            pickerView(target)
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .cancellationAction) {
            if saved == nil {
                Button("Cancel") { onDone() }.disabled(submitting)
            }
        }
        ToolbarItem(placement: .confirmationAction) {
            if saved == nil {
                Button(submitting ? "Saving…" : "Save visit") { Task { await submit() } }
                    .disabled(submitting || stamping)
            } else {
                Button("Done") { onDone() }
            }
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let e = submitError {
                Text(e).font(.labelMedium).foregroundColor(.Bad)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Color.Bad.opacity(0.08)))
            }
            addressSection
            gpsSection
            outcomeSection
            paymentSection
            Toggle("Person has moved", isOn: $moved).tint(.BrandBlue)
            LabeledField(label: "Note") {
                TextField("Note", text: $note, axis: .vertical).lineLimit(1...4)
            }
            photoSection
            paymentPhotoSection
            PrimaryButton(title: submitting ? "Saving…" : "Save visit", busy: submitting, enabled: !stamping) {
                Task { await submit() }
            }
            .padding(.top, 6)
        }
    }

    // MARK: - Sections

    @ViewBuilder private var addressSection: some View {
        if !addresses.isEmpty {
            DetailCaption("Which address are you visiting?")
            FlowLayout(spacing: 6, lineSpacing: 6) {
                ForEach(addresses) { a in
                    Chip(label: a.label, selected: slot == a.key) { slot = a.key }
                }
            }
            if let ch = chosen {
                Text("📍 " + ch.text).font(.bodySmall).foregroundColor(.TextDark)
            }
        }
    }

    private var gpsStatusText: String {
        if let e = gpsError, lastFix == nil { return e }
        guard lastFix != nil else { return "Getting GPS location…" }
        let a: String = acc.map { String(Int($0)) } ?? "?"
        if !goodFix {
            return "Getting accurate GPS… now ±" + a + " m (need ±" + String(Int(GOOD_ACC_M)) + " m). Step outside / near a window."
        }
        if let ad = address { return "GPS ±" + a + " m ✓  " + ad }
        return "GPS ±" + a + " m ✓"
    }

    @ViewBuilder private var gpsSection: some View {
        if mock {
            Text("⚠ Fake-GPS / mock location app detected — this visit will be flagged to your team lead.")
                .font(.labelMedium).foregroundColor(.Bad)
        }
        Text(gpsStatusText)
            .font(.labelSmall)
            .foregroundColor((lastFix != nil && !goodFix) || (gpsError != nil && lastFix == nil) ? .Bad : .Muted)
        if gpsError != nil && lastFix == nil {
            Button("Open Settings") { LocationTracker.shared.openSettings() }
                .font(.labelMedium)
        }
        if let f = lastFix {
            MapKitView(
                markers: [RIQMapMarker(id: "me", latitude: f.latitude, longitude: f.longitude, title: "You")],
                showsUserLocation: false,
                centerOn: CLLocationCoordinate2D(latitude: f.latitude, longitude: f.longitude),
                centerZoomMeters: 300
            )
            .frame(height: 130)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .allowsHitTesting(false)
        }
    }

    @ViewBuilder private var outcomeSection: some View {
        DetailCaption("Outcome")
        DetailChipRow(LogVisitSheet.dispositions, selected: disp) { disp = $0 }
        Toggle("Payment collected", isOn: $paid).tint(.BrandBlue)
    }

    @ViewBuilder private var paymentSection: some View {
        if paid {
            DetailAmountField(label: "Amount (₹)", text: $amount)
        }
        if paid && isCreditCard {
            DetailCaption("Paid at (credit card)")
            DetailChipRow(["STAB", "NORM"], selected: normStab) { normStab = $0 }
        }
        // Promise-to-pay date — the visit re-surfaces the case on that day (RTP is not a promise).
        if !paid && disp == "PTP" {
            DetailCaption("PTP date (promised)")
            DatePickerField(label: "Pick date", iso: ptpDate) { ptpDate = $0 }
        }
    }

    private var photoButtonTitle: String {
        if stamping { return "Stamping location…" }
        if !goodFix && !override { return "📷 Waiting for accurate GPS…" }
        if photo == nil { return "📷 Take geo-tagged photo" }
        return "Retake photo"
    }

    @ViewBuilder private var photoSection: some View {
        if let p = photo {
            Image(uiImage: p).resizable().scaledToFit()
                .frame(maxWidth: .infinity).frame(height: 180)
                .accessibilityLabel("Visit photo (geo-tagged)")
        }
        Button(action: { takePhoto() }) {
            HStack(spacing: 8) {
                if stamping { ProgressView() }
                Text(photoButtonTitle).font(.system(size: 14, weight: .semibold))
            }
            .frame(maxWidth: .infinity, minHeight: 40)
        }
        .buttonStyle(.bordered).tint(.BrandBlue)
        .disabled(!(goodFix || override) || stamping)
        if !goodFix && !override && photo == nil {
            Button("Take photo anyway (weak GPS — may be flagged)") { override = true }
                .font(.labelMedium)
        }
        if !DetailImagePicker.cameraAvailable {
            DetailCaption("No camera on this device — the photo will be picked from the library.")
        }
    }

    @ViewBuilder private var paymentPhotoSection: some View {
        if let p = paymentPhoto {
            Image(uiImage: p).resizable().scaledToFit()
                .frame(maxWidth: .infinity).frame(height: 180)
                .accessibilityLabel("Payment screenshot")
        }
        DetailCaption(paymentPhoto == nil ? "🧾 Payment screenshot (optional)" : "🧾 Payment screenshot ✓")
        HStack(spacing: 8) {
            Button(action: { picker = .paymentGallery }) {
                Text("🖼 Gallery").frame(maxWidth: .infinity, minHeight: 36)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
            Button(action: { picker = .paymentCamera }) {
                Text("📷 Camera").frame(maxWidth: .infinity, minHeight: 36)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
        }
    }

    // MARK: - Success (share)

    private func successView(_ d: VisitDraft) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill").foregroundColor(.Good).font(.system(size: 28))
                Text("Visit saved").font(.titleMedium).foregroundColor(.TextDark)
            }
            Text("Forward the visit summary and the geotagged photo to the office, a colleague or yourself.")
                .font(.bodySmall).foregroundColor(.Muted)
            if let p = photo {
                Image(uiImage: p).resizable().scaledToFit().frame(maxWidth: .infinity).frame(height: 200)
            }
            Button(action: { shareAgain(d) }) {
                Label("Share to WhatsApp…", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.borderedProminent).tint(.Good)
            Button(action: { shareToSelf(d) }) {
                Label("Send to myself", systemImage: "person.crop.circle").frame(maxWidth: .infinity, minHeight: 40)
            }
            .buttonStyle(.bordered).tint(.BrandBlue)
            PrimaryButton(title: "Done") { onDone() }
        }
    }

    private func message(_ d: VisitDraft) -> String {
        return CaseText.visitMessage(self.case, agentName: app.user?.name ?? "", draft: d)
    }

    private func shareAgain(_ d: VisitDraft) {
        Actions.shareVisit(message: message(d), photoJpeg: d.photoJpeg, paymentPhotoJpeg: d.paymentPhotoJpeg)
    }

    private func shareToSelf(_ d: VisitDraft) {
        Actions.shareVisitToSelf(selfPhone: app.user?.phone, message: message(d), photoJpeg: d.photoJpeg)
    }

    // MARK: - Pickers

    @ViewBuilder private func pickerView(_ target: VisitPickerTarget) -> some View {
        switch target {
        case .visitCamera:
            DetailImagePicker(preferCamera: true) { img in
                picker = nil
                if let i = img {
                    stamping = true
                    Task { await processVisitPhoto(i) }
                }
            }
            .ignoresSafeArea()
        case .paymentCamera:
            DetailImagePicker(preferCamera: true) { img in
                picker = nil
                if let i = img { paymentPhoto = VisitStamp.normalized(i, maxPx: 1600) }
            }
            .ignoresSafeArea()
        case .paymentGallery:
            DetailImagePicker(preferCamera: false) { img in
                picker = nil
                if let i = img { paymentPhoto = VisitStamp.normalized(i, maxPx: 1600) }
            }
            .ignoresSafeArea()
        }
    }

    private func takePhoto() {
        // Freeze the GPS the moment the photo is taken — the stamp and the visit use this reading.
        shot = lastFix
        shotAge = lastFix?.ageSeconds
        picker = .visitCamera
    }

    @MainActor
    private func processVisitPhoto(_ raw: UIImage) async {
        let f: GPSFix? = shot
        let at: GPSFix? = f ?? lastFix
        var thumb: UIImage? = nil
        if let p = at {
            thumb = await VisitStamp.mapSnapshot(lat: p.latitude, lng: p.longitude)
        }
        // Address + pincode of the EXACT spot the photo was taken (matches the stamped Lat/Lng).
        var spotAddr: String? = address
        var spotPin: String? = gpsPincode
        var spotCity: String? = gpsCity
        if let fx = f, let g = await LocationOnce.reverseGeocode(fx) {
            if let p = CaseText.nb(g.pincode) { spotPin = p }
            if let a = VisitStamp.cleanAddress(g.address, pin: g.pincode) { spotAddr = a }
            if let c = CaseText.nb(g.city) { spotCity = c }
        }
        if let p = spotPin { gpsPincode = p }
        if let a = spotAddr { address = a }
        if let c = spotCity { gpsCity = c }

        let info = VisitStampInfo(
            lat: f?.latitude ?? lastFix?.latitude,
            lng: f?.longitude ?? lastFix?.longitude,
            acc: f?.accuracy ?? lastFix?.accuracy,
            address: spotAddr,
            agentName: app.user?.name,
            caseLabel: caseLabel,
            visitedLabel: chosen?.label,
            pincode: spotPin,
            mapThumb: thumb
        )
        let upright: UIImage = VisitStamp.normalized(raw, maxPx: 1600)
        photo = VisitStamp.stamp(upright, info)
        stamping = false
    }

    // MARK: - GPS (live while the form is open)

    @MainActor
    private func gpsLoop() async {
        while !Task.isCancelled {
            do {
                let fix: GPSFix = try await LocationOnce.current(timeout: 8, desiredAccuracy: 10, maxAge: 5)
                applyFix(fix)
                gpsError = nil
            } catch let e as LocationOnceError {
                if case .denied = e {
                    gpsError = e.localizedDescription
                    return
                }
            } catch {
                // transient — keep trying
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    @MainActor
    private func applyFix(_ fix: GPSFix) {
        lastFix = fix
        if fix.isMock { mock = true }
        var needGeocode: Bool = true
        if let g = geocodedAt {
            needGeocode = fix.location.distance(from: g.location) > 50
        }
        if needGeocode {
            geocodedAt = fix
            Task { @MainActor in
                if let a = await LocationOnce.reverseGeocode(fix) {
                    if let line = CaseText.nb(a.address) { address = line }
                    if let p = CaseText.nb(a.pincode) { gpsPincode = p }
                    if let c = CaseText.nb(a.city) { gpsCity = c }
                }
            }
        }
    }

    // MARK: - Submit

    private func buildDraft(photoJpeg: Data?, paymentJpeg: Data?) -> VisitDraft {
        let n: String = note.trimmingCharacters(in: .whitespacesAndNewlines)
        var d = VisitDraft(
            lat: lastFix?.latitude, lng: lastFix?.longitude, accuracy: lastFix?.accuracy,
            personMoved: moved, paid: paid,
            amount: detailAmount(amount),
            disposition: disp, note: n.isEmpty ? nil : note, photoJpeg: photoJpeg
        )
        d.normStab = (paid && isCreditCard) ? normStab : nil
        d.ptpDate = (!paid && disp == "PTP" && !ptpDate.isEmpty) ? ptpDate : nil
        d.paymentPhotoJpeg = paymentJpeg
        d.addressSlot = addresses.isEmpty ? nil : slot
        d.addressText = chosen?.text
        d.gpsMock = (shot?.isMock ?? false) || mock
        d.gpsFixAgeS = shotAge ?? lastFix?.ageSeconds
        d.gpsPincode = gpsPincode
        d.gpsAddress = address
        d.gpsCity = gpsCity
        // The visit's GPS = the reading frozen when the photo was taken (matches the stamp).
        if photo != nil, let f = shot {
            d.lat = f.latitude
            d.lng = f.longitude
            d.accuracy = f.accuracy
        }
        return d
    }

    @MainActor
    private func submit() async {
        if submitting { return }
        let jpeg: Data? = photo?.jpegData(compressionQuality: 0.85)
        let payJpeg: Data? = paymentPhoto?.jpegData(compressionQuality: 0.85)
        let d: VisitDraft = buildDraft(photoJpeg: jpeg, paymentJpeg: payJpeg)
        submitting = true
        submitError = nil
        do {
            _ = try await API.shared.createVisit(
                caseId: self.case.id, lat: d.lat, lng: d.lng, accuracy: d.accuracy,
                personMoved: d.personMoved, paid: d.paid, amount: d.amount,
                disposition: d.disposition, note: d.note, photoJpeg: d.photoJpeg,
                normStab: d.normStab, ptpDate: d.ptpDate,
                paymentPhotoJpeg: d.paymentPhotoJpeg,
                addressSlot: d.addressSlot, gpsMock: d.gpsMock,
                gpsFixAgeS: d.gpsFixAgeS, gpsPincode: d.gpsPincode,
                gpsAddress: d.gpsAddress, gpsCity: d.gpsCity
            )
            submitting = false
            saved = d
            showToast("Visit saved")
            // Open the share sheet so the agent can forward the summary + geotagged photo (WhatsApp…).
            Actions.shareVisit(message: message(d), photoJpeg: d.photoJpeg, paymentPhotoJpeg: d.paymentPhotoJpeg)
        } catch {
            submitting = false
            submitError = CaseText.submitError(error)
        }
    }
}
