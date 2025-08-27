
from pydantic import BaseModel, EmailStr, Field, HttpUrl,constr
from datetime import datetime, date
from typing import Optional, Dict, Union, List, Literal
from app.models import RecurrenceRule
from app.enums import DeliveryType, InvoiceStatus,OrganizationType
from enum import Enum
from app.models import PriorityLevel  # SQLAlchemy model
from enum import Enum as PyEnum
from .models import SupportTicket, SupportReply
from app.enums import OrganizationType
from app.models import CustodyEventType
from datetime import date, time
from app.models import PendingRole
from uuid import UUID
import enum
from app.models import BadgeType, SubscriptionStatus
# --------------------------
# Trip Schemas
# --------------------------
class TripBase(BaseModel):
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None
    delivery_type: DeliveryType
    scheduled_time: Optional[datetime] = None
    cost: Optional[float] = None
    client_name: Optional[str] = None
    organization_id: Optional[UUID]
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    distance_km: Optional[float] = None
    status: Optional[str] = None
    vehicle_type: Optional[str] = None
    location_zone: Optional[str] = None
    shift_window: Optional[str] = None
    compliance_flag: Optional[bool] = False
    recurrence_rule: Optional[RecurrenceRule] = None
    priority: Optional[str] = None
    custom_delivery_description: Optional[str] = None

class TripCreate(TripBase):
    pass

class TripUpdate(TripBase):
    pass

class TripPatch(TripBase):
    pass

class TripResponse(TripBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --------------------------
# User Schemas
# --------------------------
class RoleEnum(str, Enum):
    user = "user"
    admin = "admin"
    driver = "driver"
    client = "client"
    super_admin = "super_admin"
    regulator = "regulator"

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.user
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: RoleEnum
    is_active: bool
    is_verified: bool
    created_at: datetime
    regulated_country:Optional[str]
    regulated_state:Optional[str]
    regulated_region:Optional[str]
    
class UserAdminOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: RoleEnum
    is_active: bool
    is_verified: bool
    organization_id: UUID
    organization_name: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class PaginatedUsers(BaseModel):
    total: int
    skip: int
    limit: int
    data: List[UserAdminOut]    
class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class UserStatusOut(BaseModel):
    name: str
    email: str
    role: str
    organization_id: Optional[UUID]
    organization_name: Optional[str]  

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    expires_in: int

# --------------------------
# Trip Analytics Schemas
# --------------------------
class TripAnalyticsFilters(BaseModel):
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: Optional[str]
    driver_id: Optional[UUID]
    client_name: Optional[str]
    delivery_type: Optional[str]

class TripAnalyticsData(BaseModel):
    total_trips: int
    total_distance_km: float
    total_cost: float
    average_cost: float
    most_common_delivery_type: Optional[str]

class TripAIPrediction(BaseModel):
    predicted_trips_next_day: int
    insight: str

class TripAnalyticsResponse(BaseModel):
    filters_applied: TripAnalyticsFilters
    analytics: TripAnalyticsData
    ai_prediction: TripAIPrediction

# --------------------------
# Proof of Delivery (POD)
# --------------------------
class PODBase(BaseModel):
    trip_id: UUID
    attachment_url: Optional[str] = None
    signature: Optional[str] = None
    notes: Optional[str] = None
    delivered_to: Optional[str] = None
    driver_id: Optional[UUID] = None

class PODCreate(PODBase):
    pass

class PODResponse(PODBase):
    id: UUID

# --------------------------
# Client Booking & Trips
# --------------------------
class ClientRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_id: UUID

class TripCreateClient(BaseModel):
    delivery_type: DeliveryType
    custom_delivery_description: Optional[str] = None
    pickup_location: str
    dropoff_location: str
    distance_km: float
    scheduled_time: datetime
    priority: str

class TripClientResponse(BaseModel):
    id: UUID
    delivery_type: DeliveryType
    custom_delivery_description: Optional[str] = None
    pickup_location: str
    dropoff_location: str
    distance_km: float
    priority: str
    scheduled_time: datetime
    created_at: datetime

class TripClientStatusUpdate(BaseModel):
    status: Literal["cancelled", "delivered", "rescheduled"]

# --------------------------
# Invoice
# --------------------------
class InvoiceCreate(BaseModel):
    client_id: Optional[UUID]
    organization_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    start_date: date
    end_date: date
    reference_code: Optional[str] = None
    generated_at: Optional[datetime] = None

class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    client_id: UUID
    organization_id: Optional[UUID] = None
    status: InvoiceStatus
    generated_at: datetime
    due_date: Optional[datetime]
    reference_code: Optional[str]
    start_date: date
    end_date: date
    amount: float

# --------------------------
# AI Optimizer
# --------------------------
class AssignDriverRequest(BaseModel):
    driver_id: UUID

class OptimizerRequest(BaseModel):
    delivery_type: str
    pickup_lat: float
    pickup_lon: float
    priority_score: float = Field(..., ge=0, le=10)
    priority: str
    client_id: UUID
    pickup_address: str
    dropoff_address: str
    estimated_cost: float

class DriverRecommendation(BaseModel):
    driver_id: UUID
    driver_name: str
    distance_km: float
    predicted_score: float

class OptimizerResponse(BaseModel):
    trip_id: UUID
    assigned_driver_id: int
    assigned_driver_name: str
    scheduled_time: datetime
    predicted_score: float
    top_3_recommendations: List[DriverRecommendation]

    class Config:
        from_attributes = True

# --------------------------
# System Configurations
# --------------------------
class VehicleTypeBase(BaseModel):
    name: str

class VehicleTypeCreate(VehicleTypeBase):
    pass

class VehicleTypeResponse(VehicleTypeBase):
    id: UUID

    class Config:
        from_attributes = True

class PriorityLevelBase(BaseModel):
    name: str

class PriorityLevelCreate(PriorityLevelBase):
    pass

class PriorityLevelResponse(PriorityLevelBase):
    id: UUID

    class Config:
        from_attributes = True

class ShiftWindowBase(BaseModel):
    name: str

class ShiftWindowCreate(ShiftWindowBase):
    pass

class ShiftWindowResponse(ShiftWindowBase):
    id: UUID

    class Config:
        from_attributes = True

class ZoneBase(BaseModel):
    name: str

class ZoneCreate(ZoneBase):
    pass

class ZoneResponse(ZoneBase):
    id: UUID

    class Config:
        from_attributes = True

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetSubmit(BaseModel):
    token: str 
    new_password: str

class PasswordChange(BaseModel):
    current_password: str 
    new_password: str

# Enum for status
class TicketStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"

# --- Input Schemas ---

class SupportTicketBase(BaseModel):
    subject: str
    message: str

class SupportTicketCreate(BaseModel):
    subject: str
    message:str
    
class SupportReplyCreate(BaseModel):
    ticket_id: UUID
    message: str

class SupportMessageCreate(BaseModel):
    ticket_id: UUID
    message: str

# --- Output Schemas ---

class SupportReplyResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    admin_id: UUID
    message: str
    created_at: datetime

    class Config:
        from_attributes = True

class SupportMessageResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    sender_id: Optional[UUID]
    message: str
    created_at: datetime

    class Config:
        from_attributes = True

class SupportTicketResponse(BaseModel):
    id: UUID
    user_id: UUID
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    replies: Optional[List[SupportReplyResponse]] = []
    messages: List[SupportMessageResponse] = []

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    question: str
    answer: str        

class PublicUserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Literal["client", "driver"]
    invite_code: str # org invite code
    accept_terms: bool 
    
class OrganizationCreate(BaseModel):
    name:str      
    type:OrganizationType
    country:str
    state:str
    region:Optional[str]=None
    ico_registered:Optional[bool]=False
    data_retention_years:Optional[int]=3
    
class OrganizationOut(BaseModel):
    id: UUID
    name: str
    invite_code: Optional[str]
    ico_registered: Optional[bool]
    data_retention_years: Optional[int]
    type: str
    is_active:bool
    created_at: datetime
    user_count: Optional[int]=None
    email: Optional[EmailStr]
    phone_number: Optional[str]
    address_line: Optional[str]
    postal_code: Optional[str]
    license_number: Optional[str]    
    
    class Config:
        from_attributes = True
    
class OrganizationUpdate(BaseModel):
    name: Optional[str]
    is_active:Optional[bool]
    email: Optional[EmailStr]
    phone_number: Optional[str]
    address_line: Optional[str]
    postal_code: Optional[str]
    license_number: Optional[str]
    waste_processing_capability: Optional[str]
    delivery_capacity: Optional[int]
    contact_person_name: Optional[str]
    contact_person_role: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    license_expiry_date: Optional[date] = None
    supported_waste_types: Optional[List[str]] = None
            

    class Config:
        from_attributes = True
        
class SuperAdminCreateUser(BaseModel):
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.user
    name: Optional[str] = None
    organization_id: Optional[UUID] = None
    

class RegulatorCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    regulated_country: str
    regulated_state: str
    regulated_region: Optional[str] = None
    
class RegulatorUpdate(BaseModel):
    organization_name: Optional[str]
    name: Optional[str]
    email: Optional[EmailStr]
    license_number: Optional[str]
    is_active: bool
    license_expiry: Optional[date]
    phone_number: Optional[str]
    address: Optional[str]
    regulated_country: Optional[str]
    regulated_state: Optional[str]
    regulated_region: Optional[str]
    regulated_waste_types: Optional[List[str]] = []
    regulated_goods_types:Optional[List[str]] = []
    regulated_logistics_scope:Optional[List[str]] = []
class RegulatorOut(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    role: str
    is_active:bool
    is_verified:bool
    organization_name: Optional[str]
    license_number: Optional[str]
    license_expiry: Optional[date]
    phone_number: Optional[str]
    address: Optional[str]
    regulated_country: Optional[str]
    regulated_state: Optional[str]
    regulated_region: Optional[str]
    regulated_waste_types: Optional[List[str]] = []
    regulated_goods_types:Optional[List[str]] = []
    regulated_logistics_scope:Optional[List[str]] = []
    class Config:
        from_attributes = True
        

class EnquiryCreate(BaseModel):
    name: str
    email: EmailStr
    message: str

class EnquiryOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
        
class IncidentCreate(BaseModel):
    title: str
    description: str
    attachment_url: Optional[str]
    incident_type: Optional[str]= None 
    location: Optional[str]= None
    severity:Optional[str]="low" # can be low, moderate, critical
    is_visible_to_regulator: Optional[bool]= False
    
class IncidentUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    incident_type: Optional[str]
    location: Optional[str]
    severity: Optional[str]
    is_visible_to_regulator: Optional[bool]
    status: Optional[str]
    attachment_url: Optional[str]    
    
class IncidentOut(BaseModel):
    id: UUID
    title: str
    description: str
    status: str
    created_at: datetime
    submitted_by_id: UUID
    organization_id: UUID
    attachment_url: Optional[str]
    is_visible_to_regulator: Optional[bool] = False
    incident_type: Optional[str] = None  # e.g., "accident", "theft", "compliance_issue"
    location: Optional[str] = None  # Optional field for incident location
    severity: Optional[str] = "low"  # New severity field

    class Config:
        from_attributes = True 
        

class AuditStatusEnum(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    escalated = "escalated"

class ComplianceStatusBase(BaseModel):
    iso_27001_certified: bool = False
    nhs_dsp_toolkit_complete: bool = False
    cyber_essentials_ready: bool = False
    has_waste_license: bool = False
    fire_risk_assessment_complete: bool = False
    gdpr_policy_uploaded: bool = False
    clinical_waste_policy_uploaded: bool = False
    sharps_policy_uploaded: bool = False
    staff_training_records_uploaded: bool = False
    transport_license_valid: bool = False
    environmental_permit_valid: bool = False
    data_protection_registration_valid: bool = False

    iso_27001_certificate_url: Optional[HttpUrl]
    waste_license_certificate_url: Optional[HttpUrl]
    gdpr_certificate_url: Optional[HttpUrl]
    environmental_permit_url: Optional[HttpUrl]
    data_protection_registration_url: Optional[HttpUrl]
    fire_risk_certificate_url: Optional[HttpUrl]

    audit_status: AuditStatusEnum = AuditStatusEnum.pending
    audit_remarks: Optional[str]
    last_audit_date: Optional[datetime]
    next_audit_due_date: Optional[datetime]
    last_updated_by_user_id: Optional[UUID]

    is_flagged_noncompliant: bool = False
    escalation_level: Optional[str] = "none"
    auto_alert_enabled: bool = True
    is_visible_to_regulator: bool = False

class ComplianceStatusCreate(ComplianceStatusBase):
    organization_id: UUID

class ComplianceStatusUpdate(ComplianceStatusBase):
    pass

class ComplianceStatusOut(ComplianceStatusBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        
class ResendVerificationRequest(BaseModel):
    email: EmailStr
    
class TwoFACodeRequest(BaseModel):
    email: str
    code: str
    
from pydantic import BaseModel, validator
from typing import Optional
from enum import Enum
from datetime import time

# Weekday Enum (must match the PostgreSQL enum)
class WeekDay(str, Enum):
    Monday = "Monday"
    Tuesday = "Tuesday"
    Wednesday = "Wednesday"
    Thursday = "Thursday"
    Friday = "Friday"
    Saturday = "Saturday"
    Sunday = "Sunday"

# 🔹 Create / Update availability
class DriverAvailabilityCreate(BaseModel):
    day_of_week: WeekDay
    start_time: time
    end_time: time

    @validator("end_time")
    def check_time(cls, end, values):
        start = values.get("start_time")
        if start and end <= start:
            raise ValueError("End time must be after start time")
        return end

# 🔹 Response model
class DriverAvailabilityOut(DriverAvailabilityCreate):
    id: UUID
    driver_id: UUID
    organization_id: UUID

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    last_updated: Optional[datetime]
    

class DriverLocationHistoryOut(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime
    trip_id: Optional[UUID] = None  # Optional link to a trip
    organization_id:UUID


    class Config:
        from_attributes = True


class ShiftAssignRequest(BaseModel):
    driver_id: UUID
    shift_date: date
    start_time: time
    end_time: time
    note: Optional[str] = None

class ShiftOut(BaseModel):
    id: UUID
    driver_id: UUID
    shift_date: date
    start_time: time
    end_time: time
    note: Optional[str]
    organization_id: UUID

    class Config:
        from_attributes = True
        
class ShiftRequestCreate(BaseModel):
    shift_id: UUID

class ShiftRequestOut(BaseModel):
    id: UUID
    shift_id: UUID
    driver_id: UUID
    status: str
    requested_at: datetime
    
class ShiftRequestUpdate(BaseModel):
    status:Literal["approved", "rejected", "pending"]   

    class Config:
        from_attributes = True

class ChainOfCustodyCreate(BaseModel):
    trip_id: UUID
    event_type: CustodyEventType
    location: Optional[str] = None
    notes: Optional[str] = None
    signed_by: Optional[str] = None
    signature_image_url: Optional[str] = None
    signature_timestamp: Optional[datetime] = None
    witness_name: Optional[str] = None

class ChainOfCustodyOut(BaseModel):
    id: UUID
    trip_id: UUID
    driver_id: Optional[UUID]
    event_type: CustodyEventType
    timestamp: datetime
    location: Optional[str]
    notes: Optional[str]
    attachment_url: Optional[str]
    signature_image_url: Optional[str]
    signature_timestamp: Optional[datetime]
    signed_by: Optional[str]
    witness_name: Optional[str]
    organization_id:UUID

    class Config:
        form_attributes = True
        
class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_path: str
    upload_time: datetime
    doc_type: Optional[str]
    organization_id:UUID
    user_id: Optional[UUID] = None # User who uploaded the document
    is_active:bool
    

class DocumentUploadOut(BaseModel):
    id: UUID
    filename: str
    file_path: str
    upload_time: datetime
    doc_type: Optional[str]
    organization_id: Optional[UUID]
    user_id: Optional[UUID]

    class Config:
        form_attributes = True


class TestimonialCreate(BaseModel):
    name: str
    content: str

class TestimonialOut(BaseModel):
    id: UUID
    name: str
    content: str
    is_approved: bool
    created_at: datetime

    class Config:
        form_attributes = True


class PendingApplicationCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: PendingRole
    message: Optional[str]= None
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None
    regulated_country: Optional[str] = None
    regulated_state: Optional[str] = None
    regulated_region: Optional[str] = None

class PendingApplicationOut(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: PendingRole
    message: Optional[str]= None
    organization_name: Optional[str]
    organization_type: Optional[str]
    regulated_country: Optional[str]
    regulated_state: Optional[str]
    regulated_region: Optional[str]
    status: str
    submitted_at: datetime

    class Config:
        form_attributes = True 
        
# Input payload when confirming delivery
class DeliveryConfirmationRequest(BaseModel):
    trip_id: UUID
    pin: str 
    signature_path: Optional[str] = None
    photo_path: Optional[str] = None
    wtn_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
# Output/response model when delivery is confirmed
class DeliveryConfirmationResponse(BaseModel):
    id: UUID
    trip_id: UUID
    pin_entered: str
    signature_image_path: Optional[str] = None
    photo_path: Optional[str] = None
    wtn_code: Optional[str] = None
    confirmed_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        form_attributes = True  # Enables ORM support for SQLAlchemy models
        
class NotificationOut(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime
    
class NotificationReadUpdate(BaseModel):
    is_read: bool    

    class Config:
        form_attributes = True 
        
class ComplianceScoreOut(BaseModel):
    organization_id: UUID
    organization_name: Optional[str] = None
    compliance_score: float
    is_compliant: bool
    flagged: bool
    next_audit_due_date: Optional[date]
    audit_status: str
    last_audit_date: Optional[date]
    escalation_level: Optional[str]
    risk_level: str
    alert: Optional[str]
    
    class Config:
        form_attributes = True  # Enables ORM support for SQLAlchemy models 
        
# For individual org compliance summary
class ComplianceSummary(BaseModel):
    organization_id: UUID
    organization_name: str
    region: Optional[str]
    iso_27001_certified: bool
    nhs_dsp_toolkit_complete: bool
    cyber_essentials_ready: bool
    has_waste_license: bool
    gdpr_policy_uploaded: bool
    clinical_waste_policy_uploaded: bool
    sharps_policy_uploaded: bool
    staff_training_records_uploaded: bool
    transport_license_valid: bool
    environmental_permit_valid: bool
    data_protection_registration_valid: bool
    audit_status: AuditStatusEnum
    last_audit_date: Optional[datetime]
    overall_compliant: bool
    last_checked: datetime

    class Config:
        form_attributes = True


# For full endpoint response
class RegulatoryComplianceSummaryResponse(BaseModel):
    total_organizations: int
    compliant_count: int
    non_compliant_count: int
    compliance_rate: str
    organization_summaries: list[ComplianceSummary]
    chart: Optional[str] = None
    
    class Config:
        form_attributes = True


# ---------- Base ----------
class DriverCredentialsBase(BaseModel):
    licence_number: str
    licence_category: Optional[str] = None
    licence_expiry: date

    adr_certificate: Optional[str] = None
    adr_expiry: Optional[date] = None
    cpc_certificate: Optional[str] = None
    cpc_expiry: Optional[date] = None
    dbs_check: Optional[str] = None
    dbs_expiry: Optional[date] = None
    medical_certificate: Optional[str] = None
    medical_expiry: Optional[date] = None

    waste_training_cert: Optional[str] = None
    infection_control_cert: Optional[str] = None
    first_aid_cert: Optional[str] = None
    first_aid_expiry: Optional[date] = None

    vehicle_insurance: Optional[str] = None
    insurance_expiry: Optional[date] = None

    employment_contract: Optional[str] = None
    right_to_work_doc: Optional[str] = None
    right_to_work_expiry: Optional[date] = None

    is_verified: bool = False
    is_active: bool = True


# ---------- Create ----------
class DriverCredentialsCreate(DriverCredentialsBase):
    user_id: UUID
    organization_id: UUID


# ---------- Update ----------
class DriverCredentialsUpdate(BaseModel):
    licence_number: Optional[str] = None
    licence_category: Optional[str] = None
    licence_expiry: Optional[date] = None

    adr_certificate: Optional[str] = None
    adr_expiry: Optional[date] = None
    cpc_certificate: Optional[str] = None
    cpc_expiry: Optional[date] = None
    dbs_check: Optional[str] = None
    dbs_expiry: Optional[date] = None
    medical_certificate: Optional[str] = None
    medical_expiry: Optional[date] = None

    waste_training_cert: Optional[str] = None
    infection_control_cert: Optional[str] = None
    first_aid_cert: Optional[str] = None
    first_aid_expiry: Optional[date] = None

    vehicle_insurance: Optional[str] = None
    insurance_expiry: Optional[date] = None

    employment_contract: Optional[str] = None
    right_to_work_doc: Optional[str] = None
    right_to_work_expiry: Optional[date] = None

    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None


# ---------- Response ----------
class DriverCredentialsOut(DriverCredentialsBase):
    id: UUID
    user_id: UUID
    organization_id: UUID

    class Config:
        form_attributes = True


# app/schemas/international_application.py
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, constr


# ---------------------------
# International Application Schemas
# ---------------------------

class BadgeType(str, Enum):
    none = "none"
    green = "green"
    blue = "blue"

class IntlBasicCreate(BaseModel):
    email: EmailStr
    name: str
    country: str
    state: str
    zip_code: str
    password:str
    confirm_password:str
    accept_terms: bool

class IntlApplicationOut(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    country: str
    state:str
    zip_code:str
    status: str
    user_id: Optional[UUID] = None
    has_paid_application_fee: bool
    created_at: datetime
    updated_at: datetime
    badge_type: BadgeType
    subscription_status: SubscriptionStatus
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None

    class Config:
        from_attributes = True


class IntlDetailsUpdate(BaseModel):
    phone_number: Optional[str] = None
    date_of_birth: Optional[str]= None
    address:Optional[str]= None
    visa_required: Optional[bool] = None
    sector: Optional[str] = None       # e.g., "health", "tech"
    role_applied_for: Optional[str] = None
    state: Optional[str] = None        # NEW (added based on your request)
    zip_code: Optional[str] = None     # NEW (added based on your request)
    # documents path
    cv_path: Optional[str]= None
    passport_path: Optional[str]= None
    driver_license_path: Optional[str] = None
    certificate_path: Optional[str] = None
    personal_statement:Optional[str]= None
    
# ---------------------------
# Payment Schemas
# ---------------------------
class PaymentCreate(BaseModel):
    application_id: UUID
    amount: float                     # using float here, db handles Decimal/Numeric
    currency: Optional[str] = "GBP"
    provider: Optional[str] = None    # e.g., "stripe", "paystack"
    reference: Optional[str] = None   # txn id or reference

class PaymentOut(BaseModel):
    id: UUID
    application_id: UUID
    amount: float
    currency: str
    provider: Optional[str]
    reference: Optional[str]
    status: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True
        

# app/schemas/analytics.py (or wherever you keep analytics schemas)
from typing import Optional, Literal, List, Dict
from pydantic import BaseModel

class DailyViewStat(BaseModel):
    date: str
    views: int

# Minimal Plotly schema so frontend can render directly with Plotly.newPlot()
class PlotlyTrace(BaseModel):
    type: Literal["scatter"] = "scatter"
    mode: Literal["lines", "lines+markers"] = "lines+markers"
    name: str = "Views"
    x: List[str]  # ISO date strings
    y: List[int]  # counts per day

class PlotlyLayout(BaseModel):
    title: str = "Application Views Over Time"
    xaxis: Dict = {"title": "Date"}
    yaxis: Dict = {"title": "Views"}
    margin: Dict = {"l": 40, "r": 20, "t": 50, "b": 40}

class PlotlyChartPayload(BaseModel):
    traces: List[PlotlyTrace]
    layout: PlotlyLayout

class ApplicationAnalyticsResponse(BaseModel):
    application_id: str
    total_views: int
    unique_organizations: Optional[int] = None
    last_viewed_at: Optional[str] = None
    views_over_time: List[DailyViewStat] = []
    extra_insights: Optional[dict] = None
    # New: chart payload for Plotly (only for premium users)
    chart: Optional[PlotlyChartPayload] = None 

    class Config:
        from_attributes = True

class SubscriptionRequest(BaseModel):
    badge_type: BadgeType  # "green" or "blue"
    
    class config:
        from_attributes = True

class DeleteAccountRequest(BaseModel):
    password: str
    reason: Optional[str] = None
    
    class config:
        from_attributes = True


# ✅ Request schema (optional — empty for now)
class RestoreUserRequest(BaseModel):
    """Reserved for future use, e.g., adding a restore reason."""
    pass


# ✅ Response schema
class RestoreUserResponse(BaseModel):
    id: UUID
    email: str
    is_active: bool
    restored_at: datetime
    restored_by: UUID  # Who performed the restore
    
    class config:
        from_attributes = True

    
class DeletedUser(BaseModel):
    id: UUID
    email: EmailStr
    deleted_at: datetime
    deletion_reason: Optional[str] = None

    class config:
        from_attributes = True
