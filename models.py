from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    phone = Column(String(15), unique=True, nullable=False)
    role = Column(String(20), default="Sales Exec")
    password = Column(String(100), nullable=False)
    active_leads_count = Column(Integer, default=0)
    capacity = Column(Integer, default=50)
    avatar = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    leads = relationship("Lead", back_populates="owner")
    bookings = relationship("Booking", back_populates="creator")

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(15), nullable=False, index=True)
    email = Column(String(100), nullable=True)
    budget = Column(String(50), nullable=True)
    source = Column(String(20), default="Walk-in")
    status = Column(String(20), default="NEW")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    project_id = Column(Integer, nullable=True)
    next_followup = Column(DateTime(timezone=True), nullable=True)
    last_contact = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    owner = relationship("User", back_populates="leads")
    bookings = relationship("Booking", back_populates="lead")
    interactions = relationship("Interaction", back_populates="lead")

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)
    type = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    units = relationship("Unit", back_populates="project")

class Unit(Base):
    __tablename__ = "units"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    tower = Column(String(50), nullable=True)
    floor = Column(Integer, nullable=True)
    number = Column(String(20), nullable=False)
    status = Column(String(20), default="Available")
    carpet_area = Column(Float, nullable=True)
    rate_per_sqft = Column(Float, nullable=True)
    booking_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    project = relationship("Project", back_populates="units")

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    project_id = Column(Integer, nullable=False)
    unit_id = Column(Integer, nullable=False)
    unit_number = Column(String(50), nullable=False)
    deal_amount = Column(Float, nullable=False)
    base_cost = Column(Float, nullable=False)
    charges = Column(JSON, default=list)  # Store as JSON array
    parking_type = Column(String(20), default="None")
    
    # Applicant details
    applicant_name = Column(String(100), nullable=False)
    applicant_phone = Column(String(15), nullable=False)
    applicant_email = Column(String(100), nullable=True)
    applicant_pan = Column(String(20), nullable=True)
    applicant_aadhar = Column(String(20), nullable=True)
    applicant_address = Column(Text, nullable=True)
    applicant_occupation = Column(String(50), nullable=True)
    
    # Co-applicant
    co_applicant_name = Column(String(100), nullable=True)
    co_applicant_phone = Column(String(15), nullable=True)
    co_applicant_pan = Column(String(20), nullable=True)
    co_applicant_aadhar = Column(String(20), nullable=True)
    
    # Payment details
    payment_mode = Column(String(20), default="Cheque")
    payment_bank = Column(String(100), nullable=True)
    payment_ref = Column(String(100), nullable=True)
    payment_date = Column(DateTime(timezone=True), nullable=True)
    booking_amount = Column(Float, nullable=True)
    
    status = Column(String(20), default="PENDING")
    remarks = Column(Text, nullable=True)
    agree_terms = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    lead = relationship("Lead", back_populates="bookings")
    creator = relationship("User", back_populates="bookings")
    payment_schedules = relationship("PaymentSchedule", back_populates="booking")
    documents = relationship("Document", back_populates="booking")

class PaymentSchedule(Base):
    __tablename__ = "payment_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    milestone = Column(String(100), nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    amount = Column(Float, nullable=False)
    payer = Column(String(20), default="Customer")
    status = Column(String(20), default="Pending")
    payment_date = Column(DateTime(timezone=True), nullable=True)
    payment_ref = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    booking = relationship("Booking", back_populates="payment_schedules")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    type = Column(String(50), nullable=False)
    file_name = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    generated = Column(Boolean, default=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    lead = relationship("Lead")
    booking = relationship("Booking", back_populates="documents")

class Interaction(Base):
    __tablename__ = "interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    type = Column(String(20), default="Note")  # Note, Visit
    notes = Column(Text, nullable=True)
    next_followup_date = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    lead = relationship("Lead", back_populates="interactions")
    # Line removed here: Base = declarative_base()
