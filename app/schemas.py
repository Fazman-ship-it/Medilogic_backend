
from pydantic import BaseModel, EmailStr, Field, HttpUrl
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
    created_at: datetime
    regulated_country:Optional[str]
    regulated_state:Optional[str]
    regulated_region:Optional[str]
    
class UserAdminOut(UserOut):
    is_active: bool
    organization_id: UUID   

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
    
class OrganizationUpdate(BaseModel):
    name: Optional[str]
    is_active:Optional[bool]    

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
        from_attribute = True
        
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
        from_attribute = True


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
    user_id: Optional[UUID] = None  # User who uploaded the document

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