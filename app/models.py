# app/models.py
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, DateTime, Text,Date,ARRAY,Numeric
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from sqlalchemy import Enum
import enum
from sqlalchemy import Enum as PgEnum
from sqlalchemy.orm import relationship
from app.enums import DeliveryType
from sqlalchemy import Text
from app.enums import InvoiceStatus
from sqlalchemy import Float
from app.enums import OrganizationType
from sqlalchemy.sql import func
from sqlalchemy import Time
from app.database import Base
from sqlalchemy.dialects.postgresql import ENUM
from enum import Enum as PyEnum
from sqlalchemy.dialects.postgresql import UUID,JSON
import uuid
from app.utilites.time_utilities import now_utc

Base = declarative_base()
class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    client = "client"
    driver = "driver"
    regulator = "regulator"
    
#Adding  New priority
class PriorityLevel(enum.Enum):
    normal = "normal"
    urgent = "urgent"
    stat = "stat"
    
#Enum for recurring trips
class RecurrenceRule(str, enum.Enum):
    none = "none"
    weekly = "weekly"
    monthly = "monthly"
    
class WeekDay(enum.Enum):
    monday = "Monday"
    tuesday = "Tuesday"
    wednesday = "Wednesday"
    thursday = "Thursday"
    friday = "Friday"
    saturday = "Saturday"
    sunday = "Sunday"    

class SeverityLevel(str,enum.Enum):
    low ="low"
    moderate = "moderate"
    critical = "critical"


class CustodyEventType(str,enum.Enum):
    pickup_confirmed = "pickup_confirmed"
    in_transit = "in_transit"
    delayed = "delayed"
    handed_off = "handed_off"
    delivered = "delivered"

class PendingRole(str,enum.Enum):
    admin = "admin"
    regulator = "regulator"

class AuditStatusEnum(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    escalated = "escalated"

class InternationalApplicationStatus(str, enum.Enum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    
class BadgeType(str,enum.Enum):
    none = "none"
    green = "green"
    blue = "blue"


# ✅ Enum for subscription lifecycle
class SubscriptionStatus(str,enum.Enum):
    active = "active"
    expired = "expired"
    cancelled = "cancelled"            
    none = "none"
    
class SubscriptionPlan(str, enum.Enum):
    free = "free"
    green = "green"
    blue = "blue"
    
class MedilogicDriverStatus(str, enum.Enum):
    submitted = "submitted"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TripStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    
    
class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_name = Column(String, nullable=True)
    delivery_type = Column(SqlEnum(DeliveryType), nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=False)
    cost = Column(Float)
    client_name = Column(String)
    pickup_location = Column(String)
    dropoff_location = Column(String)
    distance_km = Column(Float, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    location_zone = Column(String, nullable=True)
    vehicle_type = Column(String, nullable=True)
    shift_window = Column(String, nullable=True)
    compliance_flag = Column(Boolean, default=False)
    created_by = Column(String, nullable=True)
    recurrence_rule = Column(SqlEnum(RecurrenceRule), nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    receiver_name = Column(String, nullable=True)
    priority = Column(SqlEnum(PriorityLevel), default=PriorityLevel.normal, nullable=False)  # New priority field   
    pod = relationship("POD", back_populates="trip", uselist=False)
    custom_delivery_description = Column(String, nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="trips")
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    client = relationship("User", foreign_keys=[client_id], back_populates="client_trips")
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    driver= relationship("User", foreign_keys=[driver_id],back_populates="driver_trips")
    activity_logs = relationship("ActivityLog", back_populates="trip")
    custody_events = relationship("ChainOfCustody", back_populates="trip",cascade="all, delete")
    location_history = relationship("DriverLocationHistory", back_populates="trip")
    delivery_confirmations = relationship("DeliveryConfirmation", back_populates="trip", cascade="all, delete-orphan")
    confirmation_pin = Column(String, nullable=True)
    is_delivered = Column(Boolean, default=False)
    delivery_signature_path = Column(String, nullable=True)  # store image/signature
    confirmation_photo_path = Column(String, nullable=True)
    delivery_confirmed_at = Column(DateTime, nullable=True)
    delivery_ip = Column(String, nullable=True)
    wtn_serial = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False)
    notes = Column(Text, nullable=True, doc="Special instruction or notes for this trip")

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)     # ✅ Confirm this is `name`
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=True)
    organization_name = Column(String, nullable=True)  # Optional field for organization name
    logo_url = Column(String, nullable=True)  # Optional field for organization logo URL
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization",back_populates="users")
    pods =relationship("POD", back_populates="driver")
    client_trips = relationship("Trip", foreign_keys="[Trip.client_id]", back_populates="client")
    driver_trips = relationship("Trip", foreign_keys="[Trip.driver_id]", back_populates="driver")
    activity_logs= relationship("ActivityLog", back_populates="user")
    invoices = relationship("Invoice", back_populates="client")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    password_reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime(timezone=True), nullable=True)  # ✅ UTC
    is_verified =   Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)  # ✅ UTC
    support_tickets = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
    regulated_country = Column(String, nullable=True)  # Optional field for regulated country
    regulated_state = Column(String, nullable=True)  # Optional field for regulated state
    regulated_region = Column(String, nullable=True)  # Optional field for regulated region
    two_fa_code = Column(String, nullable=True)  # Optional field for 2FA code
    two_fa_expiry = Column(DateTime(timezone=True), nullable=True)  # ✅ UTC
    availabilities = relationship("DriverAvailability", back_populates="driver", cascade="all, delete")
    shifts = relationship("ShiftAssignment", back_populates="driver")
    custody_events= relationship("ChainOfCustody",back_populates="driver", cascade="all,delete")
    session_id = Column(String, nullable=True)  # Optional field for session management
    session_expires_at = Column(DateTime(timezone=True), nullable=True)  # ✅ UTC
    last_location_update = Column(DateTime(timezone=True), nullable=True)  # ✅ UTC
    location_history = relationship("DriverLocationHistory", back_populates="driver",cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user")
    testimonials = relationship("Testimonial", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user")
    credentials = relationship("DriverCredentials", back_populates="driver", uselist=False)
    license_number = Column(String, nullable=True)
    license_expiry = Column(Date, nullable=True)
    phone_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    regulated_waste_types = Column(ARRAY(String), default=[])   # e.g., ["clinical", "pharma", "hazardous"]
    regulated_goods_types = Column(ARRAY(String), default=[])   # e.g., ["surgical", "pharma products"]
    regulated_logistics_scope = Column(ARRAY(String), default=[])
    international_applications = relationship("InternationalApplication", back_populates="user")
    deleted_at = Column(DateTime(timezone=True), nullable=True) 
    deletion_reason = Column(Text, nullable=True)
    medilogic_driver = relationship("Medilogic_Driver", back_populates="user", uselist=False)
    
class POD(Base):
    __tablename__ = "pods"
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # Foreign key to User
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False)
    signature = Column(Text, nullable=True)# Optional e-signature or driver note.,
    timestamp = Column(DateTime(timezone=True), default=now_utc)
    notes = Column(Text, nullable=True)  # Optional notes from the driver or client
    delivered_to = Column(String, nullable=True)  # Name of the person who received the package
    trip = relationship("Trip", back_populates="pod")
    driver = relationship("User", back_populates="pods")
    organization_id = Column(UUID(as_uuid=True),ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="pods") 
    created_at = Column(DateTime(timezone=True), default=now_utc)
    files = relationship("PODFile", back_populates="pod", cascade="all, delete-orphan")       

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    logo_url = Column(String, nullable=True)
    users = relationship("User", back_populates="organization") 
    trips = relationship("Trip", back_populates="organization")
    invoices = relationship("Invoice", back_populates="organization")
    type = Column(PgEnum(OrganizationType), nullable=False)
    invoices = relationship("Invoice", back_populates="organization")
    pods = relationship("POD", back_populates="organization")
    activity_logs = relationship("ActivityLog", back_populates="organization")
    support_tickets = relationship("SupportTicket", back_populates="organization")
    support_replies = relationship("SupportReply", back_populates="organization")
    support_messages = relationship("SupportMessage", back_populates="organization")
    vehicle_types = relationship("VehicleType", back_populates="organization")
    shift_windows = relationship("ShiftWindow", back_populates="organization")
    zones = relationship("Zone", back_populates="organization")
    invite_code = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    country = Column(String, nullable=False)
    state = Column(String, nullable=False)
    region = Column(String, nullable=True)
    incidents = relationship("Incident", back_populates="organization")
    compliance_status = relationship("ComplianceStatus", uselist=False, back_populates="organization")
    data_retention_years = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    ico_registered = Column(Boolean, default=False)
    availabilities = relationship("DriverAvailability", back_populates="organization", cascade="all, delete")
    shift_assignments = relationship("ShiftAssignment", back_populates="organization")
    shifts = relationship("Shift", back_populates="organization",cascade="all, delete")
    enquiries = relationship("Enquiry", back_populates="organization")
    documents= relationship("Document", back_populates="organization")
    location_history =relationship("DriverLocationHistory", back_populates="organization", cascade="all, delete")
    chain_of_custody_events = relationship("ChainOfCustody", back_populates="organization", cascade="all, delete")
    delivery = relationship("DeliveryConfirmation", back_populates="organization", cascade="all, delete-orphan")
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    address_line = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    license_number = Column(String, nullable=True)
    waste_processing_capability = Column(String, nullable=True)
    delivery_capacity = Column(Integer, nullable=True)
    contact_person_name = Column(String, nullable=True)
    contact_person_role = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    driver_credentials = relationship("DriverCredentials", back_populates="organization", cascade="all, delete-orphan")
    license_expiry = Column(Date, nullable=True)  # Optional field for license expiry
    supported_waste_types = Column(ARRAY(String), nullable=True)
    applications = relationship("InternationalApplication", back_populates="organization")
    views = relationship("ApplicationView", back_populates="organization", cascade="all, delete-orphan")
    medilogic_drivers = relationship("Medilogic_Driver", back_populates="organization", cascade="all, delete-orphan")
    driver_views = relationship("DriverView", back_populates="organization", cascade="all, delete-orphan")
    daily_notifications = relationship("DailyNotification", back_populates="organization")
    ico_registration_number = Column(String, nullable=True)  # ICO registration ID if available
        
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"),nullable=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="activity_logs")    
    trip = relationship("Trip", back_populates="activity_logs")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="activity_logs")
    ip_address = Column(String, nullable=True)  # Optional field for IP address
    user_agent = Column(String, nullable=True)  # Optional field for user agent string       


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(SqlEnum(InvoiceStatus, name="invoice_status_enum"), default=InvoiceStatus.unpaid)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=True)
    reference_code = Column(String, unique=True, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date,nullable=False)
    invoice_number = Column(String, unique=True, nullable=False)
    # Relationships
    client = relationship("User", back_populates="invoices")
    organization = relationship("Organization", back_populates="invoices")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),onupdate=func.now())

class VehicleType(Base):
    __tablename__ = "vehicle_types"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="vehicle_types")        

class PriorityLevel(Base):
    __tablename__ = "priority_levels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)

class ShiftWindow(Base):
    __tablename__ = "shift_windows"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="shift_windows")        

class Zone(Base):
    __tablename__ = "zones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="zones")


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    subject = Column(String, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.open)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    user = relationship("User", back_populates="support_tickets")
    replies = relationship("SupportReply", back_populates="ticket", cascade="all, delete-orphan")
    messages = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    organization = relationship("Organization", back_populates="support_tickets")        
    is_deleted= Column(Boolean, default=False)

class SupportReply(Base):
    __tablename__ = "support_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"),index=True)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    ticket = relationship("SupportTicket", back_populates="replies")
    admin = relationship("User")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    organization = relationship("Organization", back_populates="support_replies")        
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"),index=True)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    organization = relationship("Organization", back_populates="support_messages")
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    is_deleted= Column(Boolean, default=False)
    
    
class Enquiry(Base):
    __tablename__ = "enquiries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    user = relationship("User")
    organization = relationship("Organization", back_populates="enquiries")
    
    
class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    submitted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending, resolved, escalated
    created_at = Column(DateTime(timezone=True), default=now_utc)
    organization = relationship("Organization", back_populates="incidents")
    submitted_by = relationship("User")
    incident_type = Column(String, nullable=False)  # e.g., "accident", "theft", "compliance_issue"
    location = Column(String, nullable=True)  # Optional field for incident location
    severity = Column(SqlEnum(SeverityLevel,name="severitylevel"),nullable=False, default='low')  # New severity field
    escalated= Column(Boolean, default=False)  # New field to track escalation status
    is_visible_to_regulator = Column(Boolean, default=False)  # New field to control visibility to regulators
    files = relationship("IncidentFile", back_populates="incident", cascade="all, delete-orphan")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(),default=func.now())


class ComplianceStatus(Base):
    __tablename__ = "compliance_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"),nullable=True)
    # Core certifications
    iso_27001_certified = Column(Boolean, default=False)
    nhs_dsp_toolkit_complete = Column(Boolean, default=False)
    cyber_essentials_ready = Column(Boolean, default=False)
    has_waste_license = Column(Boolean, default=False)
    # Operational compliance (for waste and clinical logistics)
    fire_risk_assessment_complete = Column(Boolean, default=False)
    gdpr_policy_uploaded = Column(Boolean, default=False)
    clinical_waste_policy_uploaded = Column(Boolean, default=False)
    sharps_policy_uploaded = Column(Boolean, default=False)
    staff_training_records_uploaded = Column(Boolean, default=False)
    transport_license_valid = Column(Boolean, default=False)
    environmental_permit_valid = Column(Boolean, default=False)
    data_protection_registration_valid = Column(Boolean, default=False)
    # Certificate & document links (stored URLs)
    iso_27001_certificate_url = Column(String, nullable=True)
    waste_license_certificate_url = Column(String, nullable=True)
    gdpr_certificate_url = Column(String, nullable=True)
    environmental_permit_url = Column(String, nullable=True)
    data_protection_registration_url = Column(String, nullable=True)
    fire_risk_certificate_url = Column(String, nullable=True)
    # Audit trail
    audit_status = Column(Enum(AuditStatusEnum), default=AuditStatusEnum.pending, nullable=False)
    audit_remarks = Column(Text, nullable=True)
    last_audit_date = Column(DateTime(timezone=True), nullable=True)
    next_audit_due_date = Column(DateTime(timezone=True), nullable=True)
    last_updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    # Risk flags and controls
    is_flagged_noncompliant = Column(Boolean, default=False)
    escalation_level = Column(String, default="none")  # none, warning, review, urgent
    auto_alert_enabled = Column(Boolean, default=True)
    flags_needs_review = Column(Boolean, default=False)
    is_visible_to_regulator = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    organization = relationship("Organization", back_populates="compliance_status")


class DriverAvailability(Base):
    __tablename__ = "driver_availabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    day_of_week = Column(Enum(WeekDay), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    driver = relationship("User", back_populates="availabilities")
    organization = relationship("Organization", back_populates="availabilities")
    

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    shift_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    note = Column(String, nullable=True)
    # Relationships
    driver = relationship("User", back_populates="shifts")
    organization = relationship("Organization", back_populates="shift_assignments")
    
class ShiftRequest(Base):
    __tablename__ = "shift_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=False)
    status = Column(String, default="pending")  # Options: pending, approved, rejected
    requested_at = Column(DateTime(timezone=True), default=now_utc)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    driver = relationship("User")
    shift = relationship("Shift", back_populates="shift_requests")
    organization = relationship("Organization")
    
class Shift(Base):
    __tablename__ = "shifts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)

    # Relationships
    shift_requests = relationship("ShiftRequest", back_populates="shift", cascade="all, delete")
    organization = relationship("Organization", back_populates="shifts")
    

class ChainOfCustody(Base):
    __tablename__ = "chain_of_custody"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # who logged it
    event_type = Column(SqlEnum(CustodyEventType, name="custodyeventtype"), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=now_utc)
    location = Column(String, nullable=True)  # optional GPS or address
    notes = Column(Text, nullable=True)
    attachment_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    signed_by = Column(String, nullable=True)
    signature_image_url = Column(String, nullable=True)
    signature_timestamp = Column(DateTime(timezone=True), default=now_utc, nullable=True)
    witness_name = Column(String, nullable=True)
    trip = relationship("Trip", back_populates="custody_events")
    driver = relationship("User", back_populates="custody_events")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="chain_of_custody_events")
    

class DriverLocationHistory(Base):
    __tablename__ = "driver_location_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=now_utc)
    driver = relationship("User", back_populates="location_history")
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"))  # Optional link to a trip
    trip = relationship("Trip", back_populates="location_history")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization=relationship("Organization", back_populates="location_history")

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    upload_time =Column(DateTime(timezone=True), default=now_utc)
    doc_type = Column(String, nullable=True)  # e.g., "license", "permit"
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    user = relationship("User", back_populates="documents")
    organization = relationship("Organization", back_populates="documents")
    credential_id = Column(UUID(as_uuid=True), ForeignKey("driver_credentials.id"), nullable=True)
    credential = relationship("DriverCredentials", back_populates="documents")
    is_active = Column(Boolean, default=True)
    expiry_date = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
    medilogic_driver_id = Column(UUID(as_uuid=True), ForeignKey("medilogic_drivers.id",ondelete="CASCADE"))
    medilogic_driver = relationship("Medilogic_Driver", back_populates="documents")
    file_size = Column(Integer, nullable=True)        # size in bytes
    mime_type = Column(String, nullable=True)
    
class Testimonial(Base):
    __tablename__ = "testimonials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Optional
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    user = relationship("User", back_populates="testimonials", lazy="joined")
    

class PendingApplication(Base):
    __tablename__ = "pending_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # Will be hashed before saving
    role = Column(SqlEnum(PendingRole, name="pendingrole"), nullable=False)
    message = Column(Text, nullable=True)
    # Admin-specific
    organization_name = Column(String, nullable=True)
    organization_type = Column(String, nullable=True)
    organization_country = Column(String, nullable=True)
    organization_state = Column(String, nullable=True)
    organization_region = Column(String, nullable=True)
    # Regulator-specific
    regulated_country = Column(String, nullable=True)
    regulated_state = Column(String, nullable=True)
    regulated_region = Column(String, nullable=True)
    
    #Compliance
    ico_registration_number = Column(String, nullable=True)  # ICO registration ID if available
    ico_registered = Column(Boolean, default=False)
    data_retention_years = Column(Integer, nullable=True)
    
    status = Column(String, default="pending")  # pending, approved, rejected
    submitted_at = Column(DateTime(timezone=True), default=now_utc)

class DeliveryConfirmation(Base):
    __tablename__ = "delivery_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"))
    pin_entered = Column(String, nullable=False)
    signature_image_path = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    wtn_code = Column(String, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), default=now_utc)
    pickup_at = Column(DateTime(timezone=True), nullable=True, default=now_utc)
    dropoff_at = Column(DateTime(timezone=True), nullable=True, default=now_utc)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    trip = relationship("Trip", back_populates="delivery_confirmations")
    organization = relationship("Organization", back_populates="delivery")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    pdf_receipt_path = Column(String, nullable=True)  # Path to generated PDF receipt
    external_client_name = Column(String, nullable=True)
    external_client_email = Column(String, nullable=True)
    external_client_signature_path = Column(String, nullable=True)
    driver_signature_path = Column(String, nullable=True)
    disposal_facility_name = Column(String, nullable=True)
    disposal_facility_address = Column(String, nullable=True)
    disposal_facility_signature_path = Column(String, nullable=True)
    pickup_photo_path = Column(String, nullable=True)    # When collected
    dropoff_photo_path = Column(String, nullable=True)   # When delivered
    attachments = Column(JSON, nullable=True)           # list of extra files
    extra_notes = Column(Text, nullable=True)
    # Access & audit
    access_token = Column(String, nullable=True, unique=True, index=True)  # token for no-login signing
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(),default=func.now())
    
    
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="general")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    user = relationship("User", back_populates="notifications")
    

class DriverCredentials(Base):
    __tablename__ = "driver_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # driver
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    # ✅ Driving license details
    licence_number = Column(String, nullable=False)
    licence_category = Column(String, nullable=True)  # e.g., B, C1, C, CE
    licence_expiry = Column(Date, nullable=False)

    # ✅ Regulatory compliance (for medical/waste transport)
    adr_certificate = Column(String, nullable=True)   # file path or S3 URL
    adr_expiry = Column(Date, nullable=True)
    cpc_certificate = Column(String, nullable=True)
    cpc_expiry = Column(Date, nullable=True)
    dbs_check = Column(String, nullable=True)         # file path
    dbs_expiry = Column(Date, nullable=True)
    medical_certificate = Column(String, nullable=True)
    medical_expiry = Column(Date, nullable=True)

    # ✅ Training certifications
    waste_training_cert = Column(String, nullable=True)
    infection_control_cert = Column(String, nullable=True)
    first_aid_cert = Column(String, nullable=True)
    first_aid_expiry = Column(Date, nullable=True)

    # ✅ Vehicle insurance
    vehicle_insurance = Column(String, nullable=True)
    insurance_expiry = Column(Date, nullable=True)

    # ✅ Employment info
    employment_contract = Column(String, nullable=True)  # upload contract file
    right_to_work_doc = Column(String, nullable=True)    # visa / permit file
    right_to_work_expiry = Column(Date, nullable=True)

    # ✅ Status flags
    is_verified = Column(Boolean, default=False)  # Admin/Org approval
    is_active = Column(Boolean, default=True)

    # Relationships
    driver = relationship("User", back_populates="credentials")
    organization = relationship("Organization", back_populates="driver_credentials")    
    documents = relationship("Document", back_populates="credential", cascade="all, delete-orphan")
    

class InternationalApplication(Base):
    __tablename__ = "international_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # submitted before approval
    email = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    country = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    status = Column(String, default=InternationalApplicationStatus.submitted, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # set on approval
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)

    # Gate fee
    has_paid_application_fee = Column(Boolean, default=False)
    application_fee_payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    application_fee_payment = relationship("Payment",foreign_keys=[application_fee_payment_id],uselist=False)  # single payment
    payments = relationship("Payment",back_populates="application",cascade="all, delete-orphan",foreign_keys="Payment.application_id")
    # Post-approval details (nullable until filled)
    email = Column(String, nullable=True)
    name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    country = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    state = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    phone_number = Column(String, nullable=True)
    visa_required = Column(Boolean, nullable=True)
    sector = Column(String, nullable=True)  # "health" | "tech" | etc.
    role_applied_for = Column(String, nullable=True)  # "nurse", "doctor", "software developer", etc.
        
    # gated uploads (file paths)
    cv_path = Column(String, nullable=True)
    passport_path = Column(String, nullable=True)
    drivers_license_path = Column(String, nullable=True)
    personal_statement_path = Column(String, nullable=True)
    certificate_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
   #relationship
    user = relationship("User", back_populates="international_applications")
    organization = relationship("Organization", back_populates="applications")
    views = relationship("ApplicationView", back_populates="application", cascade="all, delete-orphan")
    badge_type = Column(SqlEnum(BadgeType, name="badgetype"),default=BadgeType.none,nullable=False)
    subscription_status = Column(SqlEnum(SubscriptionStatus, name="subscriptionstatus"),default=SubscriptionStatus.expired,nullable=False)
    subscription_start_date = Column(DateTime(timezone=True), nullable=True)
    subscription_end_date = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    
    
class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("international_applications.id"), nullable=False)
    medilogic_driver_id = Column(UUID(as_uuid=True),ForeignKey("medilogic_drivers.id", ondelete="CASCADE"),nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="GBP", nullable=False)
    provider = Column(String, nullable=True)     # e.g. "stripe", "paystack"
    reference = Column(String, nullable=True)    # provider reference / txn id
    status = Column(String, default="succeeded") # keep simple for now
    created_at = Column(DateTime(timezone=True), default=now_utc)
    is_verified = Column(Boolean, default=False) # confired via provider webhook
    medilogic_driver = relationship("Medilogic_Driver", back_populates="payments")
    application = relationship("InternationalApplication", back_populates="payments", foreign_keys=[application_id])
    payment_type = Column(String, nullable=False)  # e.g., "application_fee", "subscription", "one_time"
    
# models.py
class ApplicationView(Base):
    __tablename__ = "application_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("international_applications.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    viewed_at = Column(DateTime(timezone=True), default=now_utc)
    #Releationship
    application = relationship("InternationalApplication", back_populates="views")
    organization = relationship("Organization", back_populates="views") 


# -----------------------------------
# Driver Model
# -----------------------------------
class Medilogic_Driver(Base):
    __tablename__ ="medilogic_drivers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone_number = Column(String, nullable=False)
    address = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    country = Column(String, nullable=False)
    state = Column(String, nullable=False)
    region = Column(String, nullable=True)
    license_number = Column(String, nullable=False)
    license_expiry = Column(Date, nullable=False)
    vehicle_type = Column(String, nullable=False)  # e.g., "van", "truck"
    zip_code = Column(String, nullable=True)
    experience_years = Column(Integer, nullable=True)
    preferred_role = Column(String, nullable=False)  # e.g. "waste driver", "medical delivery"
    status = Column(SqlEnum(MedilogicDriverStatus, name="driverstatus"), default=MedilogicDriverStatus.submitted, nullable=False)
    subscription_status = Column(SqlEnum(SubscriptionStatus, name="subscriptionstatus"), default=SubscriptionStatus.none, nullable=False)
    subscription_plan = Column(SqlEnum(SubscriptionPlan, name="subscriptionplan"), default=SubscriptionPlan.free, nullable=False)
    badge_type = Column(SqlEnum(BadgeType, name="badgetype"),default=BadgeType.none,nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    user = relationship("User", back_populates="medilogic_driver")
    organization = relationship("Organization", back_populates="medilogic_drivers")
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    documents = relationship("Document", back_populates="medilogic_driver", cascade="all, delete-orphan")
    views = relationship("DriverView", back_populates="medilogic_driver", cascade="all, delete-orphan")
    subscription_start = Column(DateTime(timezone=True), nullable=True)
    subscription_end = Column(DateTime(timezone=True), nullable=True)
    payments = relationship("Payment", back_populates="medilogic_driver", cascade="all, delete-orphan")
    #Document paths
    drivers_license = Column(String, nullable=True)
    dvla_check_code = Column(String, nullable=True)
    proof_of_id_address = Column(String, nullable=True)
    mot_certificate = Column(String, nullable=True)
    vehicle_insurance = Column(String, nullable=True)
    waste_carrier_license = Column(String, nullable=True)
    adr_certificate = Column(String, nullable=True)
    dbs_check = Column(String, nullable=True)
    professional_id_photo = Column(String, nullable=True)
    can_view_analytics = Column(Boolean, default=False)
    can_see_org_names = Column(Boolean, default=False)
    can_upload_docs = Column(Boolean, default=False)
    stripe_customer_id = Column(String, nullable=True)      # Stripe Customer ID
    stripe_subscription_id = Column(String, nullable=True)  # Stripe Subscription ID
    stripe_price_id = Column(String, nullable=True)         # Stripe Price ID for the plan
    cancel_at_period_end = Column(Boolean, default=False)   # if subscription is set to cancel
    
    
class DriverView(Base):
    __tablename__ ="driver_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medilogic_driver_id = Column(UUID(as_uuid=True), ForeignKey("medilogic_drivers.id", ondelete="CASCADE"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    viewed_at = Column(DateTime(timezone=True), default=now_utc)
    medilogic_driver = relationship("Medilogic_Driver", back_populates="views")
    organization = relationship("Organization", back_populates="driver_views")
    


class DailyNotification(Base):
    __tablename__ = "daily_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    is_ai_generated = Column(Boolean, default=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="daily_notifications")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization = relationship("Organization", back_populates="daily_notifications")
    is_active_today = Column(Boolean, default=False)
    

class PODFile(Base):
    __tablename__ = "pod_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    pod_id = Column(UUID(as_uuid=True), ForeignKey("pods.id", ondelete="CASCADE"))
    s3_key = Column(String, nullable=False)  # path in S3
    file_type = Column(String, nullable=True)  # e.g. "raw", "pdf", "receipt"
    pod = relationship("POD", back_populates="files")
    
class IncidentFile(Base):
    __tablename__ = "incident_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    s3_key = Column(String, nullable=False)
    file_type = Column(String, nullable=True)  # e.g., "image", "pdf", "docx"
    incident = relationship("Incident", back_populates="files")

class TripNotification(Base):
    __tablename__ = "trip_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"))
    notification_type = Column(String, nullable=False)  # "1_day_left", "4_hours_left", etc.
    sent_at = Column(DateTime(timezone=True), default=now_utc)