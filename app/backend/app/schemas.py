from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, EmailStr, ConfigDict, Field


# ---------- Auth / Users ----------
class UserBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str = "telecaller"
    branch: Optional[str] = None
    banks: List[str] = []
    assigned_pincodes: List[str] = []
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
    banks: Optional[List[str]] = None
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
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
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
    account_no: Optional[str] = None
    card_no: Optional[str] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    alt_phone: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bucket: Optional[str] = None
    cycle: Optional[str] = None
    month: Optional[str] = None
    total_outstanding: Decimal = Decimal("0")
    principal_outstanding: Decimal = Decimal("0")
    min_amount_due: Decimal = Decimal("0")
    funding_amount: Decimal = Decimal("0")
    received_amount: Decimal = Decimal("0")
    pending_amount: Decimal = Decimal("0")


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
    allocation_reason: Optional[str]
    last_contacted_at: Optional[datetime] = None
    follow_up_date: Optional[date] = None
    propensity: Optional[int] = None
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


# ---------- AI ----------
class AIRequest(BaseModel):
    prompt: str
    context: Optional[str] = None


class AIResponse(BaseModel):
    reply: str


class AllocateRequest(BaseModel):
    only_unallocated: bool = True
    bank: Optional[str] = None
