from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Date, Boolean, ForeignKey, Text, JSON, Float,
    UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


# Roles: "admin", "fos" (field officer), "telecaller"
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, index=True, nullable=False)
    phone = Column(String(20))
    hashed_password = Column(String(255))
    google_sub = Column(String(120), unique=True, nullable=True)
    role = Column(String(20), nullable=False, default="telecaller")
    emp_code = Column(String(20), unique=True, index=True, nullable=True)  # e.g. TC001 — caller ID used in upload sheets
    branch = Column(String(80))                 # e.g. Vizag, Hyderabad
    team_lead_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # FOS/caller → their team lead
    banks = Column(JSON, default=list)          # ["ICICI","RBL","AXIS"]
    assigned_products = Column(JSON, default=list)  # ["PL X BKT","BL X BKT","DR"] — FOS product coverage
    assigned_pincodes = Column(JSON, default=list)  # ["530001","530016"]
    home_lat = Column(Float)                    # base location for GPS allocation
    home_lng = Column(Float)
    # HRMS profile
    employment_type = Column(String(30))        # Full-time / Part-time / Contract
    joining_date = Column(Date, nullable=True)
    address = Column(Text)
    emergency_contact = Column(String(60))
    photo_url = Column(String(255))
    is_active = Column(Boolean, default=True)   # False = blocked / left → login denied, hidden from active pickers
    blocked_reason = Column(String(200))        # why the account was blocked (e.g. "left org", "on hold")
    blocked_at = Column(DateTime, nullable=True)
    blocked_by = Column(Integer, nullable=True) # id of the HR/HO/admin who blocked them
    # Full manpower / HR record (from the SSDE manpower sheet)
    designation = Column(String(80))            # real job title (Field Executive, HR Manager...)
    location = Column(String(80))               # duty location / region
    hr_ref = Column(String(30))                 # official employee id (SSD0001)
    gender = Column(String(10))
    dob = Column(Date, nullable=True)
    blood_group = Column(String(8))
    marital_status = Column(String(20))
    ctc = Column(String(30))
    emergency_name = Column(String(80))
    emergency_relation = Column(String(30))
    dra_status = Column(String(20))
    pvc_status = Column(String(20))
    aadhar_number = Column(String(20))
    pan_number = Column(String(20))
    bank_holder = Column(String(120))
    bank_account = Column(String(40))
    ifsc_code = Column(String(20))
    bank_name = Column(String(80))
    aadhar_address = Column(Text)
    current_address = Column(Text)
    rent_own = Column(String(10))
    # Dual role: a caller/FOS can ALSO be a team lead. They keep their primary role/emp_code
    # and get a second team-lead ID (tl_emp_code). On login they pick which "view" to use and
    # can switch anytime — one hat at a time (the active view drives all scoping).
    also_team_lead = Column(Boolean, default=False)
    tl_emp_code = Column(String(20), nullable=True)      # e.g. TL014, alongside FO012 / TC003
    # E-ID / profile lifecycle: staff may edit their own profile ONCE after first login.
    profile_completed = Column(Boolean, default=False)   # they finished their one-time edit
    must_change_password = Column(Boolean, default=False)
    # Brute-force protection
    failed_login_count = Column(Integer, default=0)
    lockout_until = Column(DateTime(timezone=True), nullable=True)
    # Two-factor (TOTP authenticator app)
    totp_secret = Column(String(64), nullable=True)
    twofa_enabled = Column(Boolean, default=False)
    # WebAuthn passkey ceremony challenge (transient)
    webauthn_challenge = Column(String(255), nullable=True)
    # Telecaller live-sheet layout (visible columns, order, widths, custom formula columns)
    sheet_prefs = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    visits = relationship("Visit", back_populates="officer")
    pings = relationship("LocationPing", back_populates="officer")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    # identity
    bank = Column(String(40), index=True)       # ICICI / RBL / AXIS
    branch = Column(String(80))
    # True only when a branch/location was EXPLICITLY chosen at upload (drives portfolio
    # branch-splitting). A branch inherited from the case's FOS leaves this False, so those
    # cases stay merged in one bank→product portfolio.
    branch_explicit = Column(Boolean, default=False)
    product = Column(String(80))                 # bank product, e.g. "2 BKT", "180+", "DR"
    segment = Column(String(30))                 # "Credit Card" or "PL/BL" (chosen at upload)
    account_no = Column(String(60), index=True)
    card_no = Column(String(40))
    customer_name = Column(String(160))
    phone = Column(String(20))
    alt_phone = Column(String(20))
    address = Column(Text)                        # ADD 1 (primary address line)
    address2 = Column(Text)                        # ADD 2 (+ ADD 3) — kept separate
    pincode = Column(String(10), index=True)
    # Field-corrected contact: a caller / head-office user adds the customer's latest
    # address / phone discovered mid-cycle. Surfaced to the assigned FOS (+ notified).
    new_address = Column(Text)
    new_phone = Column(String(20))
    new_contact_by = Column(String(120))          # who last updated it (name)
    new_contact_at = Column(DateTime)             # when
    latitude = Column(Float)
    longitude = Column(Float)

    # bucket / cycle
    bucket = Column(String(30))                  # 3RD BKT / X-BKT
    cycle = Column(String(10))
    month = Column(String(20))                   # free-text month from the sheet (legacy)

    # Monthly lifecycle: the period a case belongs to (chosen at upload) and the date it
    # closes out of the live views into admin-only history (per product closing rule).
    period = Column(String(7), index=True)       # "YYYY-MM"
    close_date = Column(Date, index=True)        # last day it shows to FOS/caller/etc.
    closing_type = Column(String(12))            # cyc / month_end / due_date

    # amounts (Decimal, 2dp)
    total_outstanding = Column(Numeric(14, 2), default=0)
    principal_outstanding = Column(Numeric(14, 2), default=0)
    min_amount_due = Column(Numeric(14, 2), default=0)
    funding_amount = Column(Numeric(14, 2), default=0)     # committed / target
    received_amount = Column(Numeric(14, 2), default=0)    # AMOUNT collected (= CASH COLL)
    pending_amount = Column(Numeric(14, 2), default=0)

    # MIS core fields (from the CC/MAIN loading sheet)
    enr = Column(Numeric(14, 2), default=0)               # End Net Receivables = EMI 0/S + CURR_BAL
    norm_amount = Column(Numeric(14, 2), default=0)       # NORM target amount
    stab_amount = Column(Numeric(14, 2), default=0)       # STAB (settlement) target amount
    rollback_amount = Column(Numeric(14, 2), default=0)   # ROLLBACK target (2/3/4 BKT products)
    norm_stab = Column(String(10))                        # "NORM" / "STAB" / "ROLLBACK" — paid category
    caller_name = Column(String(80), index=True)          # CALLER (as named in the sheet)
    fos_name = Column(String(120), index=True)            # FOS NAME (name/area,phone text)
    team = Column(String(40), index=True)                 # AREA / region code (GTR, KDP, TS...)
    team_lead = Column(String(40), index=True)            # TEAM column — caller team lead (SAMBA...)
    cat = Column(String(20), index=True)                  # CAT ALLO category (J / I / C ...)
    visited = Column(Boolean, default=False)              # FOS logged a visit
    extra = Column(JSON, default=dict)                    # free-form caller-added sheet columns

    # workflow
    status = Column(String(30), default="new", index=True)   # new/allocated/in_progress/paid/unpaid/ptp/closed
    paid_status = Column(String(20), default="UNPAID")       # PAID / UNPAID / PARTIAL
    disposition = Column(String(60))                          # RTP, PTP, RNR, NC, WRONG NO...
    remarks = Column(Text)
    final_status = Column(String(40))

    # telecaller follow-up workflow
    last_contacted_at = Column(DateTime(timezone=True), nullable=True)   # last call logged
    follow_up_date = Column(Date, nullable=True, index=True)             # day the case is next due in the queue

    # allocation
    assigned_fos_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_caller_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    allocation_reason = Column(String(120))

    # Caution flag — a red mark drawing attention to a case that needs manual review
    # (e.g. an old RTP "Refuse to Pay" that was wrongly sitting in PTP).
    flagged = Column(Boolean, default=False, index=True)
    flag_reason = Column(String(160))

    # escalation — pulled off the FOS/caller by admin/manager/backend to handle personally.
    # Excluded from the FOS/caller's individual performance, but STILL counted in MIS & feedback.
    escalated = Column(Boolean, default=False, index=True)
    escalated_to = Column(Integer, ForeignKey("users.id"), nullable=True)   # who owns it now
    escalated_by = Column(Integer, nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)

    # Soft delete — head office can remove cases (bad/duplicate loads); they move to the
    # "Removed cases" bin, drop out of every list/MIS/dashboard, and can be restored.
    removed = Column(Boolean, default=False, index=True)
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removed_by = Column(Integer, nullable=True)

    # who last changed this case (any field / cell / reassignment) and when
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_name = Column(String(120))

    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    fos = relationship("User", foreign_keys=[assigned_fos_id])
    caller = relationship("User", foreign_keys=[assigned_caller_id])
    visits = relationship("Visit", back_populates="case", cascade="all, delete-orphan")
    calls = relationship("CallLog", back_populates="case", cascade="all, delete-orphan")

    @property
    def closed(self) -> bool:
        """True once the case has passed its close date (cycle day / month-end / due date).
        A closed case stays visible for the rest of its month but is LOCKED — field/calling
        staff can no longer act on it. Admin can still edit for corrections."""
        if not self.close_date:
            return False
        from datetime import timedelta
        today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
        return self.close_date < today


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    officer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    latitude = Column(Float)                 # GPS where the photo was taken
    longitude = Column(Float)
    gps_accuracy = Column(Float)
    distance_from_case_m = Column(Float)     # metres between visit GPS and case location (geo-fence)
    photo_path = Column(String(255))         # gps-camera image
    location_correct = Column(Boolean)       # is the address correct?
    person_moved = Column(Boolean, default=False)

    paid = Column(Boolean, default=False)
    amount_collected = Column(Numeric(14, 2), default=0)
    disposition = Column(String(60))         # PAID/PTP/NOT AVAILABLE/MOVED/DISPUTE...
    note = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    case = relationship("Case", back_populates="visits")
    officer = relationship("User", back_populates="visits")


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    caller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    disposition = Column(String(60))          # RTP/PTP/RNR/SWITCHED OFF/WRONG NO...
    ptp_amount = Column(Numeric(14, 2), default=0)
    ptp_date = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    case = relationship("Case", back_populates="calls")


class LocationPing(Base):
    __tablename__ = "location_pings"

    id = Column(Integer, primary_key=True, index=True)
    officer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float)
    speed = Column(Float)
    active_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    officer = relationship("User", back_populates="pings")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255))
    bank = Column(String(40))
    product = Column(String(80))                     # the portfolio this upload loaded into
    sheet = Column(String(80))
    rows_total = Column(Integer, default=0)
    rows_imported = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class EmployeeDocument(Base):
    """HR document vault — one row per uploaded file for an employee (PAN, Aadhaar, …)."""
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    doc_type = Column(String(40), index=True)         # pan / aadhaar / photo / signature / ...
    filename = Column(String(255))                    # original filename
    ref = Column(String(400))                         # storage reference (/uploads/.. or gcs://..)
    content_type = Column(String(100))
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=utcnow)


class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    leave_type = Column(String(20))                 # Casual / Sick / Earned / Unpaid
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, default=0)
    reason = Column(Text)
    status = Column(String(20), default="pending", index=True)   # pending / approved / rejected
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", foreign_keys=[user_id])


class MessageTemplate(Base):
    """Reusable WhatsApp/SMS/email template with merge fields like {name}, {bank}, {pending}."""
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120))
    channel = Column(String(20), default="whatsapp")   # whatsapp / sms / email
    body = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class LegalCase(Base):
    """Litigation record for a borrower — Sec 138 / SARFAESI / Arbitration etc."""
    __tablename__ = "legal_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    borrower_name = Column(String(160))
    bank = Column(String(40))
    matter_type = Column(String(40))          # Sec 138 / SARFAESI / Arbitration / IBC / Civil / Criminal
    court = Column(String(160))
    case_number = Column(String(80))
    stage = Column(String(80))                # Notice / Filed / Evidence / Arguments / Order ...
    filed_date = Column(Date, nullable=True)
    next_hearing_date = Column(Date, nullable=True, index=True)
    status = Column(String(20), default="open")   # open / closed / won / lost / settled
    amount = Column(Numeric(14, 2), default=0)
    notes = Column(Text)
    branch = Column(String(80))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Device(Base):
    """A browser/phone a user logs in from. New devices (beyond the first) must be
    approved by an admin/manager before login is allowed — anti-attendance-fraud."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String(80), nullable=False, index=True)   # client-generated stable id
    label = Column(String(160))                                  # user agent / friendly name
    approved = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), default=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User")


class WebAuthnCredential(Base):
    """A registered passkey / biometric credential (Face ID, fingerprint, security key)."""
    __tablename__ = "webauthn_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    credential_id = Column(String(400), unique=True, index=True, nullable=False)  # base64url
    public_key = Column(Text, nullable=False)                                     # base64url COSE key
    sign_count = Column(Integer, default=0)
    transports = Column(String(120))
    label = Column(String(120))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_used = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class MisTarget(Base):
    """Per-employee monthly target % for a product's MIS (manager-entered)."""
    __tablename__ = "mis_targets"

    id = Column(Integer, primary_key=True, index=True)
    bank = Column(String(40), index=True)
    product = Column(String(80), index=True)
    emp_name = Column(String(120), index=True)
    target_pct = Column(Numeric(6, 2), default=0)     # e.g. 30 means 30%
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FeedbackEntry(Base):
    """Daily feedback row a caller/back-office maintains per case, to hand to the bank.
    One row per (case, day). Log-derived fields are auto-filled from the latest call /
    visit and remain editable; manual edits are preserved."""
    __tablename__ = "feedback_entries"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True, nullable=False)
    bank = Column(String(40), index=True)
    product = Column(String(80), index=True)
    day = Column(Date, index=True)                     # feedback day (IST)

    agency_name = Column(String(160))                  # AGENCY NAME
    visited = Column(String(20))                       # Visited / Not Visited
    dispo_code = Column(String(40))                    # Dispo Code
    visit_date = Column(String(20))                    # Visit Date
    nature_of_business = Column(String(60))            # Nature Of Business
    default_reason = Column(String(60))                # Default Reason
    tc_code = Column(String(30))                       # Tc Code
    fe_code = Column(String(30))                       # Fe Code
    tc_final_code = Column(String(30))                 # Tc Final Code
    fe_final_code = Column(String(30))                 # Fe Final Code
    tc_remarks = Column(Text)                          # Tc Remarks
    fe_remark = Column(Text)                           # Fe Remark
    ptp_date = Column(String(20))                      # PTP Date

    edited = Column(JSON, default=dict)                # {field: true} — fields a human overrode
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    case = relationship("Case")
    __table_args__ = (UniqueConstraint("case_id", "day", name="uq_feedback_case_day"),)


class CatalogProduct(Base):
    """Admin-added banks / products, merged on top of the built-in catalog. Lets the
    agency onboard a new bank or product (with its closing rule) without a code change.
    A row with product=NULL just registers a new bank name in the dropdown."""
    __tablename__ = "catalog_products"

    id = Column(Integer, primary_key=True, index=True)
    bank = Column(String(60), index=True, nullable=False)
    product = Column(String(80))                       # NULL = bank-only entry
    segment = Column(String(30))                       # suggested segment (Credit Card / PL/BL)
    closing_type = Column(String(12))                  # cyc / month_end / due_date
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Immutable record of every mutating action in the system — who did what, when,
    to which case, and the before/after value. Powers the admin/manager Activity Log
    with branch / role / employee filters. Never edited after write."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    at = Column(DateTime(timezone=True), default=utcnow, index=True)

    # who
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_name = Column(String(120))
    actor_role = Column(String(20), index=True)

    # what
    action = Column(String(40), index=True)        # reassign / deallocate / transfer / edit /
                                                   # cell_edit / paid / unpaid / payment / visit /
                                                   # call / delete / restore / escalate / import / login
    entity_type = Column(String(20), default="case", index=True)   # case / staff / import ...
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # e.g. reassigned-to

    # denormalised context so the log filters/reads without extra joins
    branch = Column(String(80), index=True)
    bank = Column(String(40), index=True)
    product = Column(String(80), index=True)

    field = Column(String(60))                     # which field/cell changed (for edits)
    old_value = Column(Text)
    new_value = Column(Text)
    detail = Column(Text)                          # human summary
    meta = Column(JSON, default=dict)              # anything extra (case_ids, counts...)


class Notification(Base):
    """A message delivered to one user (e.g. a FOS) — currently used when a caller /
    head-office updates a customer's new address or phone on one of their cases."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # recipient
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    type = Column(String(30), default="contact_update", index=True)
    title = Column(String(160))
    body = Column(Text)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    created_by = Column(String(120))               # who triggered it (name)


class SupportTicket(Base):
    """A help/support query raised by any user; handled by the hidden 'techsupport' role.
    The back-and-forth is kept as a list of messages so both sides can reply."""
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)   # who raised it
    user_name = Column(String(120))
    user_role = Column(String(30))
    branch = Column(String(80))
    category = Column(String(40), default="other")                 # login / data / bug / feature / other
    subject = Column(String(200))
    status = Column(String(20), default="open", index=True)         # open / in_progress / resolved
    messages = Column(JSON, default=list)                           # [{by_id,name,role,text,at,kind}]
    resolved_by = Column(Integer, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
