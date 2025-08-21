# app/models.py
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, DateTime, Text,Date,ARRAY
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
from sqlalchemy.dialects.postgresql import UUID
import uuid
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
        

class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_name = Column(String, nullable=True)
    delivery_type = Column(SqlEnum(DeliveryType), nullable=False)
    scheduled_time = Column(DateTime)
    cost = Column(Float)
    client_name = Column(String)
    pickup_location = Column(String)
    dropoff_location = Column(String)
    distance_km = Column(Float, nullable=True)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)     # ✅ Confirm this is `name`
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)
    Updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    reset_token_expiry = Column(DateTime, nullable= True)
    is_verified =   Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    support_tickets = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
    regulated_country = Column(String, nullable=True)  # Optional field for regulated country
    regulated_state = Column(String, nullable=True)  # Optional field for regulated state
    regulated_region = Column(String, nullable=True)  # Optional field for regulated region
    two_fa_code = Column(String, nullable=True)  # Optional field for 2FA code
    two_fa_expiry = Column(DateTime, nullable=True)  # Optional field
    availabilities = relationship("DriverAvailability", back_populates="driver", cascade="all, delete")
    shifts = relationship("ShiftAssignment", back_populates="driver")
    custody_events= relationship("ChainOfCustody",back_populates="driver", cascade="all,delete")
    session_id = Column(String, nullable=True)  # Optional field for session management
    session_expires_at = Column(DateTime, nullable=True)  # Optional field for session expiry
    last_location_update = Column(DateTime, nullable=True)
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

class POD(Base):
    __tablename__ = "pods"
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # Foreign key to User
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False)
    attachment_url = Column(String, nullable=True)  # Optional photo proof
    signature = Column(Text, nullable=True)# Optional e-signature or driver note.,
    timestamp = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)  # Optional notes from the driver or client
    delivered_to = Column(String, nullable=True)  # Name of the person who received the package
    trip = relationship("Trip", back_populates="pod")
    driver = relationship("User", back_populates="pods")
    organization_id = Column(UUID(as_uuid=True),ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="pods")        

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
    created_at = Column(DateTime, default=datetime.utcnow)
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
        
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"),nullable=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=True)
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
    generated_at = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    reference_code = Column(String, unique=True, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date,nullable=False)
    invoice_number = Column(String, unique=True, nullable=False)
    # Relationships
    client = relationship("User", back_populates="invoices")
    organization = relationship("Organization", back_populates="invoices")

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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    subject = Column(String, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.open)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="support_tickets")
    replies = relationship("SupportReply", back_populates="ticket", cascade="all, delete-orphan")
    messages = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="support_tickets")        


class SupportReply(Base):
    __tablename__ = "support_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"))
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket = relationship("SupportTicket", back_populates="replies")
    admin = relationship("User")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="support_replies")        
    

class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"))
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="support_messages")
    
class Enquiry(Base):
    __tablename__ = "enquiries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    attachment_url = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, resolved, escalated
    created_at = Column(DateTime, default=datetime.utcnow)
    organization = relationship("Organization", back_populates="incidents")
    submitted_by = relationship("User")
    incident_type = Column(String, nullable=False)  # e.g., "accident", "theft", "compliance_issue"
    location = Column(String, nullable=True)  # Optional field for incident location
    severity = Column(SqlEnum(SeverityLevel,name="severitylevel"),nullable=False, default='low')  # New severity field
    escalated= Column(Boolean, default=False)  # New field to track escalation status
    is_visible_to_regulator = Column(Boolean, default=False)  # New field to control visibility to regulators


class ComplianceStatus(Base):
    __tablename__ = "compliance_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
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
    last_audit_date = Column(DateTime, nullable=True)
    next_audit_due_date = Column(DateTime, nullable=True)
    last_updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    # Risk flags and controls
    is_flagged_noncompliant = Column(Boolean, default=False)
    escalation_level = Column(String, default="none")  # none, warning, review, urgent
    auto_alert_enabled = Column(Boolean, default=True)
    flags_needs_review = Column(Boolean, default=False)
    is_visible_to_regulator = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    requested_at = Column(DateTime, default=datetime.utcnow)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    driver = relationship("User")
    shift = relationship("Shift", back_populates="shift_requests")
    organization = relationship("Organization")
    
class Shift(Base):
    __tablename__ = "shifts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
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
    timestamp = Column(DateTime, default=datetime.utcnow)
    location = Column(String, nullable=True)  # optional GPS or address
    notes = Column(Text, nullable=True)
    attachment_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    signed_by = Column(String, nullable=True)
    signature_image_url = Column(String, nullable=True)
    signature_timestamp = Column(DateTime, nullable=True)
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
    timestamp = Column(DateTime, default=datetime.utcnow)
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
    upload_time = Column(DateTime, default=datetime.utcnow)
    doc_type = Column(String, nullable=True)  # e.g., "license", "permit"
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    user = relationship("User", back_populates="documents")
    organization = relationship("Organization", back_populates="documents")
    credential_id = Column(UUID(as_uuid=True), ForeignKey("driver_credentials.id"), nullable=True)
    credential = relationship("DriverCredentials", back_populates="documents")
    is_active = Column(Boolean, default=True)
    expiry_date = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
    
class Testimonial(Base):
    __tablename__ = "testimonials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Optional
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    # Regulator-specific
    regulated_country = Column(String, nullable=True)
    regulated_state = Column(String, nullable=True)
    regulated_region = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, approved, rejected
    submitted_at = Column(DateTime, default=datetime.utcnow)
    
class DeliveryConfirmation(Base):
    __tablename__ = "delivery_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"))
    pin_entered = Column(String, nullable=False)
    signature_image_path = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    wtn_code = Column(String, nullable=True)
    confirmed_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    trip = relationship("Trip", back_populates="delivery_confirmations")
    organization = relationship("Organization", back_populates="delivery")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="general")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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