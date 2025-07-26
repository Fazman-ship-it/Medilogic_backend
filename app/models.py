# app/models.py
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, DateTime, Text,Date
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


class CustodyEventType(str, enum.Enum):
    pickup_confirmed = "pickup_confirmed"
    in_transit = "in_transit"
    delayed = "delayed"
    handed_off = "handed_off"
    delivered = "delivered"

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    organization = relationship("Organization", back_populates="trips")
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    client = relationship("User", foreign_keys=[client_id], back_populates="client_trips")
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    driver= relationship("User", foreign_keys=[driver_id],back_populates="driver_trips")
    activity_logs = relationship("ActivityLog", back_populates="trip")
    custody_events = relationship("ChainOfCustody", back_populates="trip",cascade="all, delete")
    location_history = relationship("DriverLocationHistory", back_populates="trip")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
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
    organization_id = Column(Integer,ForeignKey("organizations.id"))
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
class POD(Base):
    __tablename__ = "pods"
    driver_id = Column(Integer, ForeignKey("users.id"))  # Foreign key to User
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    attachment_url = Column(String, nullable=True)  # Optional photo proof
    signature = Column(Text, nullable=True)# Optional e-signature or driver note.,
    timestamp = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)  # Optional notes from the driver or client
    delivered_to = Column(String, nullable=True)  # Name of the person who received the package
    trip = relationship("Trip", back_populates="pod")
    driver = relationship("User", back_populates="pods")
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="pods")        

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
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
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="activity_logs")    
    trip = relationship("Trip", back_populates="activity_logs")
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="activity_logs")
    ip_address = Column(String, nullable=True)  # Optional field for IP address
    user_agent = Column(String, nullable=True)  # Optional field for user agent string       


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
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
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="vehicle_types")        

class PriorityLevel(Base):
    __tablename__ = "priority_levels"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

class ShiftWindow(Base):
    __tablename__ = "shift_windows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="shift_windows")        

class Zone(Base):
    __tablename__ = "zones"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="zones")


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    subject = Column(String, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.open)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="support_tickets")
    replies = relationship("SupportReply", back_populates="ticket", cascade="all, delete-orphan")
    messages = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan")
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="support_tickets")        


class SupportReply(Base):
    __tablename__ = "support_replies"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    admin_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket = relationship("SupportTicket", back_populates="replies")
    admin = relationship("User")
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="support_replies")        
    

class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"))
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")
    organization_id = Column(Integer,ForeignKey("organizations.id"))
    organization = relationship("Organization", back_populates="support_messages")
    
class Enquiry(Base):
    __tablename__ = "enquiries"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    user = relationship("User")
    organization = relationship("Organization", back_populates="enquiries")
    
    
class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    submitted_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False)
    iso_27001_certified = Column(Boolean, default=False)
    nhs_dsp_toolkit_complete = Column(Boolean, default=False)
    cyber_essentials_ready = Column(Boolean, default=False)
    has_waste_license = Column(Boolean, default=False)
    last_audit_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization = relationship("Organization", back_populates="compliance_status")
    

class DriverAvailability(Base):
    __tablename__ = "driver_availabilities"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    day_of_week = Column(Enum(WeekDay), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    driver = relationship("User", back_populates="availabilities")
    organization = relationship("Organization", back_populates="availabilities")
    

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    note = Column(String, nullable=True)
    # Relationships
    driver = relationship("User", back_populates="shifts")
    organization = relationship("Organization", back_populates="shift_assignments")
    
class ShiftRequest(Base):
    __tablename__ = "shift_requests"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    status = Column(String, default="pending")  # Options: pending, approved, rejected
    requested_at = Column(DateTime, default=datetime.utcnow)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    driver = relationship("User")
    shift = relationship("Shift", back_populates="shift_requests")
    organization = relationship("Organization")
    
class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # Relationships
    shift_requests = relationship("ShiftRequest", back_populates="shift", cascade="all, delete")
    organization = relationship("Organization", back_populates="shifts")
    

class ChainOfCustody(Base):
    __tablename__ = "chain_of_custody"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # who logged it
    event_type = Column(PgEnum(CustodyEventType), nullable=False)
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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    organization = relationship("Organization", back_populates="chain_of_custody_events")
    

class DriverLocationHistory(Base):
    __tablename__ = "driver_location_history"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    driver = relationship("User", back_populates="location_history")
    trip_id = Column(Integer, ForeignKey("trips.id"))  # Optional link to a trip
    trip = relationship("Trip", back_populates="location_history")
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    organization=relationship("Organization", back_populates="location_history")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    doc_type = Column(String, nullable=True)  # e.g., "license", "permit"
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user = relationship("User", back_populates="documents")
    organization = relationship("Organization", back_populates="documents")
    
    
class Testimonial(Base):
    __tablename__ = "testimonials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Optional
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="testimonials", lazy="joined")   