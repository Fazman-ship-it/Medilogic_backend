
from pydantic import BaseModel, EmailStr, Field
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
# --------------------------
# Trip Schemas
# --------------------------
class TripBase(BaseModel):
    driver_id: Optional[int] = None
    driver_name: Optional[str] = None
    delivery_type: DeliveryType
    scheduled_time: Optional[datetime] = None
    cost: Optional[float] = None
    client_name: Optional[str] = None
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
    id: int
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
    id: int
    name: str
    email: EmailStr
    role: RoleEnum
    created_at: datetime
    regulated_country:Optional[str]
    regulated_state:Optional[str]
    regulated_region:Optional[str]
    
class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class UserStatusOut(BaseModel):
    name: str
    email: str
    role: str
    organization_id: Optional[int]
    organization_name: Optional[str]  

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --------------------------
# Trip Analytics Schemas
# --------------------------
class TripAnalyticsFilters(BaseModel):
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: Optional[str]
    driver_id: Optional[int]
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
    trip_id: int
    attachment_url: Optional[str] = None
    signature: Optional[str] = None
    notes: Optional[str] = None
    delivered_to: Optional[str] = None
    driver_id: Optional[int] = None

class PODCreate(PODBase):
    pass

class PODResponse(PODBase):
    id: int

# --------------------------
# Client Booking & Trips
# --------------------------
class ClientRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_id: int

class TripCreateClient(BaseModel):
    delivery_type: DeliveryType
    custom_delivery_description: Optional[str] = None
    pickup_location: str
    dropoff_location: str
    distance_km: float
    scheduled_time: datetime
    priority: str

class TripClientResponse(BaseModel):
    id: int
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
    client_id: Optional[int]
    organization_id: Optional[int] = None
    due_date: Optional[datetime] = None
    start_date: date
    end_date: date
    reference_code: Optional[str] = None
    generated_at: Optional[datetime] = None

class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    client_id: int
    organization_id: Optional[int] = None
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
    driver_id: int

class OptimizerRequest(BaseModel):
    delivery_type: str
    pickup_lat: float
    pickup_lon: float
    priority_score: float = Field(..., ge=0, le=10)
    priority: str
    client_id: int
    pickup_address: str
    dropoff_address: str
    estimated_cost: float

class DriverRecommendation(BaseModel):
    driver_id: int
    driver_name: str
    distance_km: float
    predicted_score: float

class OptimizerResponse(BaseModel):
    trip_id: int
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
    id: int

    class Config:
        from_attributes = True

class PriorityLevelBase(BaseModel):
    name: str

class PriorityLevelCreate(PriorityLevelBase):
    pass

class PriorityLevelResponse(PriorityLevelBase):
    id: int

    class Config:
        from_attributes = True

class ShiftWindowBase(BaseModel):
    name: str

class ShiftWindowCreate(ShiftWindowBase):
    pass

class ShiftWindowResponse(ShiftWindowBase):
    id: int

    class Config:
        from_attributes = True

class ZoneBase(BaseModel):
    name: str

class ZoneCreate(ZoneBase):
    pass

class ZoneResponse(ZoneBase):
    id: int

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
    ticket_id: int
    message: str

class SupportMessageCreate(BaseModel):
    ticket_id: int
    message: str

# --- Output Schemas ---

class SupportReplyResponse(BaseModel):
    id: int
    ticket_id: int
    admin_id: int
    message: str
    created_at: datetime

    class Config:
        from_attributes = True

class SupportMessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_id: Optional[int]
    message: str
    created_at: datetime

    class Config:
        from_attributes = True

class SupportTicketResponse(BaseModel):
    id: int
    user_id: int
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
    id: int
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
    organization_id: Optional[int] = None
    

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
    id: int
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
    id: int
    title: str
    description: str
    status: str
    created_at: datetime
    submitted_by_id: int
    organization_id: int
    attachment_url: Optional[str]
    is_visible_to_regulator: Optional[bool] = False
    incident_type: Optional[str] = None  # e.g., "accident", "theft", "compliance_issue"
    location: Optional[str] = None  # Optional field for incident location
    severity: Optional[str] = "low"  # New severity field

    class Config:
        from_attributes = True 
        
class ComplianceStatusBase(BaseModel):
    iso_27001_certified: Optional[bool] = False
    nhs_dsp_toolkit_complete: Optional[bool] = False
    cyber_essentials_ready: Optional[bool] = False
    has_waste_license: Optional[bool] = False
    last_audit_date: Optional[date] = None

class ComplianceStatusCreate(ComplianceStatusBase):
    organization_id: int

class ComplianceStatusUpdate(ComplianceStatusBase):
    pass

class ComplianceStatusOut(ComplianceStatusBase):
    id: int
    organization_id: int
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
    id: int
    driver_id: int
    organization_id: int

    class Config:
        from_attribute = True

from datetime import date, time

class ShiftAssignRequest(BaseModel):
    driver_id: int
    shift_date: date
    start_time: time
    end_time: time
    note: Optional[str] = None

class ShiftOut(BaseModel):
    id: int
    driver_id: int
    shift_date: date
    start_time: time
    end_time: time
    note: Optional[str]
    organization_id: int

    class Config:
        from_attributes = True
        
class ShiftRequestCreate(BaseModel):
    shift_id: int

class ShiftRequestOut(BaseModel):
    id: int
    shift_id: int
    driver_id: int
    status: str
    requested_at: datetime
    
class ShiftRequestUpdate(BaseModel):
    status:Literal["approved", "rejected", "pending"]   

    class Config:
        from_attributes = True

class ChainOfCustodyCreate(BaseModel):
    trip_id: int
    event_type: CustodyEventType
    location: Optional[str] = None
    notes: Optional[str] = None
    signed_by: Optional[str] = None
    signature_image_url: Optional[str] = None
    signature_timestamp: Optional[datetime] = None
    witness_name: Optional[str] = None

class ChainOfCustodyOut(BaseModel):
    id: int
    trip_id: int
    driver_id: Optional[int]
    event_type: CustodyEventType
    timestamp: datetime
    location: Optional[str]
    notes: Optional[str]
    attachment_url: Optional[str]
    signature_image_url: Optional[str]
    signature_timestamp: Optional[datetime]
    signed_by: Optional[str]
    witness_name: Optional[str]

    class Config:
        form_attributes = True 
