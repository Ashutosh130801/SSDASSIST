from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


# ---------- Auth / Users ----------
class UserBase(BaseModel):
    name: str
    email: str        # plain string — internal logins may use non-RFC domains (e.g. .local)
    phone: Optional[str] = None
    role: str = "telecaller"
    branch: Optional[str] = None
    team_lead_id: Optional[int] = None    # the team lead this FOS/caller reports to
    # Tolerate NULL from older rows (columns added via ALTER TABLE default to NULL, not []).
    banks: Optional[List[str]] = []
    assigned_products: Optional[List[str]] = []
    assigned_pincodes: Optional[List[str]] = []
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    employment_type: Optional[str] = None
    joining_date: Optional[date] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    photo_url: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    branch: Optional[str] = None
    team_lead_id: Optional[int] = None
    banks: Optional[List[str]] = None
    assigned_products: Optional[List[str]] = None
    assigned_pincodes: Optional[List[str]] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    employment_type: Optional[str] = None
    joining_date: Optional[date] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    photo_url: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    emp_code: Optional[str] = None
    team_lead_name: Optional[str] = None    # resolved name of the team lead (display only)
    # Dual-role (caller/FOS who is also a team lead)
    also_team_lead: Optional[bool] = None
    tl_emp_code: Optional[str] = None
    available_views: Optional[List[str]] = None   # hats this account can switch between
    active_view: Optional[str] = None             # the hat currently in effect
    is_active: bool

    # Never emit null for these — the native app parses them as non-null (a NULL from an
    # older DB row would otherwise fail JSON decoding on the phone).
    @field_validator("also_team_lead", mode="before")
    @classmethod
    def _atl_bool(cls, v):
        return bool(v)

    @field_validator("must_change_password", "profile_completed", mode="before")
    @classmethod
    def _flag_bool(cls, v):
        return bool(v)
    must_change_password: Optional[bool] = None
    profile_completed: Optional[bool] = None
    designation: Optional[str] = None
    location: Optional[str] = None
    photo_url: Optional[str] = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: str        # plain string — internal logins may use non-RFC domains (e.g. .local)
    password: str
    device_id: Optional[str] = None
    device_label: Optional[str] = None
    otp: Optional[str] = None          # TOTP 2FA code, when the account has 2FA enabled


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    device_id: str
    label: Optional[str]
    approved: bool
    last_seen: datetime
    created_at: datetime
    user_name: Optional[str] = None
    user_branch: Optional[str] = None


class LeaveCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    leave_type: Optional[str]
    start_date: date
    end_date: date
    days: int
    reason: Optional[str]
    status: str
    approver_id: Optional[int]
    decided_at: Optional[datetime]
    created_at: datetime
    user_name: Optional[str] = None
    user_branch: Optional[str] = None
    approver_name: Optional[str] = None


class TemplateCreate(BaseModel):
    name: str
    channel: str = "whatsapp"
    body: str


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    channel: str
    body: str
    created_at: datetime


class LegalCreate(BaseModel):
    case_id: Optional[int] = None
    borrower_name: Optional[str] = None
    bank: Optional[str] = None
    matter_type: str
    court: Optional[str] = None
    case_number: Optional[str] = None
    stage: Optional[str] = None
    filed_date: Optional[date] = None
    next_hearing_date: Optional[date] = None
    status: str = "open"
    amount: Decimal = Decimal("0")
    notes: Optional[str] = None
    branch: Optional[str] = None


class LegalUpdate(BaseModel):
    borrower_name: Optional[str] = None
    bank: Optional[str] = None
    matter_type: Optional[str] = None
    court: Optional[str] = None
    case_number: Optional[str] = None
    stage: Optional[str] = None
    filed_date: Optional[date] = None
    next_hearing_date: Optional[date] = None
    status: Optional[str] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
    branch: Optional[str] = None


class LegalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: Optional[int]
    borrower_name: Optional[str]
    bank: Optional[str]
    matter_type: Optional[str]
    court: Optional[str]
    case_number: Optional[str]
    stage: Optional[str]
    filed_date: Optional[date]
    next_hearing_date: Optional[date]
    status: str
    amount: Decimal
    notes: Optional[str]
    branch: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class GoogleLogin(BaseModel):
    id_token: str


# ---------- Cases ----------
class CaseBase(BaseModel):
    bank: Optional[str] = None
    branch: Optional[str] = None
    product: Optional[str] = None
    segment: Optional[str] = None
    # MIS fields
    enr: Optional[Decimal] = Decimal("0")
    norm_amount: Optional[Decimal] = Decimal("0")
    stab_amount: Optional[Decimal] = Decimal("0")
    norm_stab: Optional[str] = None
    caller_name: Optional[str] = None
    fos_name: Optional[str] = None
    team: Optional[str] = None
    team_lead: Optional[str] = None
    cat: Optional[str] = None
    visited: Optional[bool] = None
    visited_today: Optional[bool] = None
    contacted_today: Optional[bool] = None
    escalated: Optional[bool] = None
    escalated_to: Optional[int] = None
    extra: Optional[dict] = None
    account_no: Optional[str] = None
    card_no: Optional[str] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    alt_phone: Optional[str] = None
    address: Optional[str] = None
    address2: Optional[str] = None
    new_address: Optional[str] = None
    new_phone: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bucket: Optional[str] = None
    cycle: Optional[str] = None
    month: Optional[str] = None
    total_outstanding: Optional[Decimal] = Decimal("0")
    principal_outstanding: Optional[Decimal] = Decimal("0")
    min_amount_due: Optional[Decimal] = Decimal("0")
    funding_amount: Optional[Decimal] = Decimal("0")
    received_amount: Optional[Decimal] = Decimal("0")
    pending_amount: Optional[Decimal] = Decimal("0")


class CaseCreate(CaseBase):
    pass


class CaseUpdate(BaseModel):
    status: Optional[str] = None
    paid_status: Optional[str] = None
    disposition: Optional[str] = None
    remarks: Optional[str] = None
    final_status: Optional[str] = None
    received_amount: Optional[Decimal] = None
    assigned_fos_id: Optional[int] = None
    assigned_caller_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    pincode: Optional[str] = None


class CaseOut(CaseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    paid_status: Optional[str]
    disposition: Optional[str]
    remarks: Optional[str]
    final_status: Optional[str]
    assigned_fos_id: Optional[int]
    assigned_caller_id: Optional[int]
    # resolved assignee contact (for Call FOS / Call Caller buttons)
    assigned_fos_name: Optional[str] = None
    assigned_fos_phone: Optional[str] = None
    assigned_caller_name: Optional[str] = None
    assigned_caller_phone: Optional[str] = None
    allocation_reason: Optional[str]
    new_contact_by: Optional[str] = None
    new_contact_at: Optional[datetime] = None
    removed: Optional[bool] = None
    removed_at: Optional[datetime] = None
    last_contacted_at: Optional[datetime] = None
    follow_up_date: Optional[date] = None
    propensity: Optional[int] = None
    period: Optional[str] = None
    close_date: Optional[date] = None
    closing_type: Optional[str] = None
    closed: Optional[bool] = None
    rollback_amount: Optional[Decimal] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime]


# ---------- Visits ----------
class VisitCreate(BaseModel):
    case_id: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gps_accuracy: Optional[float] = None
    location_correct: Optional[bool] = None
    person_moved: bool = False
    paid: bool = False
    amount_collected: Decimal = Decimal("0")
    disposition: Optional[str] = None
    note: Optional[str] = None


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    officer_id: int
    latitude: Optional[float]
    longitude: Optional[float]
    photo_path: Optional[str]
    location_correct: Optional[bool]
    person_moved: Optional[bool]
    paid: Optional[bool]
    amount_collected: Decimal
    disposition: Optional[str]
    note: Optional[str]
    distance_from_case_m: Optional[float] = None
    created_at: datetime


# ---------- Calls ----------
class CallCreate(BaseModel):
    case_id: int
    disposition: str
    ptp_amount: Decimal = Decimal("0")
    ptp_date: Optional[date] = None          # when a PTP is promised
    follow_up_date: Optional[date] = None    # when to call back for non-PTP outcomes
    paid_amount: Decimal = Decimal("0")      # amount collected if disposition is PAID
    norm_stab: Optional[str] = None          # NORM / STAB paid (credit-card cases)
    note: Optional[str] = None


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    caller_id: int
    disposition: str
    ptp_amount: Decimal
    ptp_date: Optional[datetime]
    note: Optional[str]
    created_at: datetime


# ---------- Tracking ----------
class PingCreate(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    active_case_id: Optional[int] = None


class PingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    officer_id: int
    latitude: float
    longitude: float
    accuracy: Optional[float]
    active_case_id: Optional[int]
    created_at: datetime


class OfficerLocation(BaseModel):
    officer_id: int
    name: str
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    active_case_id: Optional[int] = None
    last_seen: datetime
    branch: Optional[str] = None
    banks: List[str] = []


# ---------- AI ----------
class AIRequest(BaseModel):
    prompt: str
    context: Optional[str] = None


class AIResponse(BaseModel):
    reply: str


class AllocateRequest(BaseModel):
    only_unallocated: bool = True
    bank: Optional[str] = None
