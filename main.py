from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import aiofiles
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_

import models
from database import engine, get_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Initialize FastAPI
app = FastAPI(title="Property CRM API", version="1.0.0")

from database import Base, engine
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crm.jaydevelopers.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create upload directories
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "kyc").mkdir(exist_ok=True)
(UPLOAD_DIR / "cheques").mkdir(exist_ok=True)
(UPLOAD_DIR / "documents").mkdir(exist_ok=True)

# Pydantic Models
class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: str
    role: str = "Sales Exec"
    password: str
    capacity: int = 50

class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    budget: Optional[str] = None
    source: str = "Walk-in"
    project_id: Optional[int] = None
    owner_id: Optional[int] = None

class LeadStatusUpdate(BaseModel):
    status: str

class AssignLeadRequest(BaseModel):
    user_id: int

class BookingCreate(BaseModel):
    lead_id: int
    project_id: int
    unit_id: int
    unit_number: str
    deal_amount: float
    base_cost: float
    charges: List[Dict] = []
    parking_type: str = "None"
    applicant_name: str
    applicant_phone: str
    applicant_email: Optional[str] = None
    applicant_pan: Optional[str] = None
    applicant_aadhar: Optional[str] = None
    applicant_address: Optional[str] = None
    applicant_occupation: Optional[str] = None
    co_applicant_name: Optional[str] = None
    co_applicant_phone: Optional[str] = None
    co_applicant_pan: Optional[str] = None
    co_applicant_aadhar: Optional[str] = None
    payment_mode: str = "Cheque"
    payment_bank: Optional[str] = None
    payment_ref: Optional[str] = None
    payment_date: Optional[str] = None
    booking_amount: Optional[float] = None
    remarks: Optional[str] = None
    agree_terms: bool = False

class InteractionCreate(BaseModel):
    lead_id: int
    type: str = "Note"
    notes: str
    next_followup_date: Optional[str] = None

class PaymentRecord(BaseModel):
    booking_id: int
    milestone: str
    amount: Optional[float] = None
    payment_ref: Optional[str] = None
    payment_date: Optional[str] = None
    payer: str = "Customer"

# Helper Functions
def add_default_data(db: Session):
    """Add default data if database is empty"""
    # Check if users exist
    user_count = db.query(models.User).count()
    
    if user_count == 0:
        # Add default admin user
        admin_user = models.User(
            name="Admin",
            email="admin@realty.com",
            phone="9876543210",
            role="Manager",
            password="password",
            capacity=50,
            avatar="A"
        )
        db.add(admin_user)
        
        # Add default project
        project = models.Project(
            name="Sunrise Apartments",
            location="Nashik",
            type="12 Floors • 4 Units/Floor"
        )
        db.add(project)
        db.flush()  # Get the ID
        
        # Add sample units
        for floor in range(1, 6):
            for unit_num in range(1, 5):
                unit = models.Unit(
                    project_id=project.id,
                    tower="Wing A",
                    floor=floor,
                    number=f"{floor}0{unit_num}",
                    status="Available",
                    carpet_area=1000,
                    rate_per_sqft=6500
                )
                db.add(unit)
        
        db.commit()

# Initialize default data on startup
@app.on_event("startup")
def startup_event():
    db = None
    try:
        db = next(get_db())
        add_default_data(db)
    except Exception as e:
        print(f"Startup warning: {e}")
    finally:
        if db:
            db.close()


# ----- AUTHENTICATION -----

@app.post("/api/auth/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Find user by phone or email
    user = db.query(models.User).filter(
        or_(
            models.User.phone == username,
            models.User.email == username
        ),
        models.User.password == password,
        models.User.is_active == True
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "access_token": "test-token-123",
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "active_leads_count": user.active_leads_count,
            "capacity": user.capacity,
            "avatar": user.avatar
        }
    }

@app.get("/api/auth/me")
async def get_current_user(db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == 1).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar,
        "email": user.email,
        "phone": user.phone,
        "is_active": user.is_active
    }

# ----- LEADS -----

@app.get("/api/leads")
async def get_leads(
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Lead)
    
    if status:
        query = query.filter(models.Lead.status == status)
    
    if owner_id:
        query = query.filter(models.Lead.owner_id == owner_id)
    
    leads = query.order_by(desc(models.Lead.created_at)).all()
    
    return [
        {
            "id": lead.id,
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "budget": lead.budget,
            "source": lead.source,
            "status": lead.status,
            "owner_id": lead.owner_id,
            "project_id": lead.project_id,
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        }
        for lead in leads
    ]

@app.get("/api/leads/unassigned")
async def get_unassigned_leads(db: Session = Depends(get_db)):
    leads = db.query(models.Lead)\
        .filter(models.Lead.owner_id == None)\
        .order_by(desc(models.Lead.created_at))\
        .all()
    
    return [
        {
            "id": lead.id,
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "budget": lead.budget,
            "source": lead.source,
            "status": lead.status,
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        }
        for lead in leads
    ]

@app.post("/api/leads")
async def create_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    # Check if phone already exists
    existing = db.query(models.Lead).filter(models.Lead.phone == lead.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already exists")
    
    new_lead = models.Lead(
        name=lead.name,
        phone=lead.phone,
        email=lead.email,
        budget=lead.budget,
        source=lead.source,
        status="NEW",
        project_id=lead.project_id,
        owner_id=lead.owner_id
    )
    
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)
    
    return {
        "id": new_lead.id,
        "name": new_lead.name,
        "phone": new_lead.phone,
        "email": new_lead.email,
        "budget": new_lead.budget,
        "source": new_lead.source,
        "status": new_lead.status,
        "owner_id": new_lead.owner_id,
        "created_at": new_lead.created_at.isoformat() if new_lead.created_at else None
    }

@app.post("/api/leads/{lead_id}/assign")
async def assign_lead(
    lead_id: int, 
    assign_data: AssignLeadRequest,
    db: Session = Depends(get_db)
):
    # Get lead
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get user
    user = db.query(models.User).filter(models.User.id == assign_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check capacity
    if user.active_leads_count >= user.capacity:
        raise HTTPException(status_code=400, detail="User has reached capacity")
    
    # Update lead
    lead.owner_id = assign_data.user_id
    lead.status = "IN_PROGRESS"
    lead.last_contact = datetime.now()
    
    # Update user's lead count
    user.active_leads_count += 1
    
    db.commit()
    
    return {"success": True, "message": "Lead assigned"}

@app.post("/api/leads/{lead_id}/status")
async def update_lead_status(
    lead_id: int, 
    status_data: LeadStatusUpdate,
    db: Session = Depends(get_db)
):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    lead.status = status_data.status
    lead.last_contact = datetime.now()
    
    if status_data.status == "BOOKED":
        lead.next_followup = None
    
    db.commit()
    
    return {"success": True, "message": "Status updated"}

# ----- USERS -----

@app.get("/api/users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(models.User)\
        .filter(models.User.is_active == True)\
        .all()
    
    return [
        {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "active_leads_count": user.active_leads_count,
            "capacity": user.capacity,
            "avatar": user.avatar
        }
        for user in users
    ]

# ----- INVENTORY -----

@app.get("/api/inventory/projects")
async def get_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    return [
        {
            "id": project.id,
            "name": project.name,
            "location": project.location,
            "type": project.type
        }
        for project in projects
    ]

@app.get("/api/inventory/project/{project_id}/towers")
async def get_towers(project_id: int, db: Session = Depends(get_db)):
    towers = db.query(models.Unit.tower)\
        .filter(
            models.Unit.project_id == project_id,
            models.Unit.tower != None
        )\
        .distinct()\
        .all()
    
    return [{"id": i+1, "name": tower[0]} for i, tower in enumerate(towers)]

@app.get("/api/inventory/tower/{tower_name}/floors")
async def get_floors(tower_name: str, db: Session = Depends(get_db)):
    floors = db.query(models.Unit)\
        .filter(
            models.Unit.tower == tower_name
        )\
        .order_by(models.Unit.floor.desc())\
        .all()
    
    # Group by floor
    floor_map = {}
    for unit in floors:
        if unit.floor not in floor_map:
            floor_map[unit.floor] = []
        
        floor_map[unit.floor].append({
            "id": unit.id,
            "number": unit.number,
            "status": unit.status
        })
    
    result = []
    for floor_num, units in sorted(floor_map.items(), reverse=True):
        result.append({
            "id": floor_num,
            "number": floor_num,
            "units": units
        })
    
    return result

# ----- BOOKINGS -----

@app.get("/api/booking")
async def get_bookings(db: Session = Depends(get_db)):
    bookings = db.query(models.Booking)\
        .order_by(desc(models.Booking.created_at))\
        .all()
    
    result = []
    for booking in bookings:
        result.append({
            "id": booking.id,
            "lead_name": booking.applicant_name,
            "project_name": "Sunrise Apartments",
            "unit_number": booking.unit_number,
            "deal_amount": booking.deal_amount,
            "status": booking.status
        })
    
    return result

@app.get("/api/booking/lead/{lead_id}")
async def get_booking_by_lead(lead_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking)\
        .filter(models.Booking.lead_id == lead_id)\
        .first()
    
    if not booking:
        return {}
    
    return {
        "id": booking.id,
        "lead_id": booking.lead_id,
        "project_id": booking.project_id,
        "unit_id": booking.unit_id,
        "unit_number": booking.unit_number,
        "deal_amount": booking.deal_amount,
        "base_cost": booking.base_cost,
        "charges": booking.charges,
        "parking_type": booking.parking_type,
        "applicant_name": booking.applicant_name,
        "applicant_phone": booking.applicant_phone,
        "applicant_email": booking.applicant_email,
        "applicant_pan": booking.applicant_pan,
        "applicant_aadhar": booking.applicant_aadhar,
        "applicant_address": booking.applicant_address,
        "applicant_occupation": booking.applicant_occupation,
        "co_applicant_name": booking.co_applicant_name,
        "co_applicant_phone": booking.co_applicant_phone,
        "co_applicant_pan": booking.co_applicant_pan,
        "co_applicant_aadhar": booking.co_applicant_aadhar,
        "payment_mode": booking.payment_mode,
        "payment_bank": booking.payment_bank,
        "payment_ref": booking.payment_ref,
        "payment_date": booking.payment_date.isoformat() if booking.payment_date else None,
        "booking_amount": booking.booking_amount,
        "status": booking.status,
        "remarks": booking.remarks,
        "agree_terms": booking.agree_terms
    }

@app.post("/api/booking")
async def create_booking(
    booking_data: BookingCreate,
    db: Session = Depends(get_db)
):
    try:
        # Parse payment date
        payment_date = None
        if booking_data.payment_date:
            try:
                payment_date = datetime.fromisoformat(booking_data.payment_date.replace("Z", "+00:00"))
            except:
                payment_date = datetime.now()
        
        # Create booking
        new_booking = models.Booking(
            lead_id=booking_data.lead_id,
            project_id=booking_data.project_id,
            unit_id=booking_data.unit_id,
            unit_number=booking_data.unit_number,
            deal_amount=booking_data.deal_amount,
            base_cost=booking_data.base_cost,
            charges=booking_data.charges,
            parking_type=booking_data.parking_type,
            applicant_name=booking_data.applicant_name,
            applicant_phone=booking_data.applicant_phone,
            applicant_email=booking_data.applicant_email,
            applicant_pan=booking_data.applicant_pan,
            applicant_aadhar=booking_data.applicant_aadhar,
            applicant_address=booking_data.applicant_address,
            applicant_occupation=booking_data.applicant_occupation,
            co_applicant_name=booking_data.co_applicant_name,
            co_applicant_phone=booking_data.co_applicant_phone,
            co_applicant_pan=booking_data.co_applicant_pan,
            co_applicant_aadhar=booking_data.co_applicant_aadhar,
            payment_mode=booking_data.payment_mode,
            payment_bank=booking_data.payment_bank,
            payment_ref=booking_data.payment_ref,
            payment_date=payment_date,
            booking_amount=booking_data.booking_amount,
            status="PENDING",
            remarks=booking_data.remarks,
            agree_terms=booking_data.agree_terms,
            created_by=1
        )
        
        db.add(new_booking)
        db.flush()  # Get the booking ID
        
        # Update unit status
        unit = db.query(models.Unit).filter(models.Unit.id == booking_data.unit_id).first()
        if unit:
            unit.status = "Blocked"
            unit.booking_id = new_booking.id
        
        # Update lead status
        lead = db.query(models.Lead).filter(models.Lead.id == booking_data.lead_id).first()
        if lead:
            lead.status = "BOOKED"
            lead.next_followup = None
        
        # Create payment schedule
        schedules = [
            {
                "milestone": "Booking Token",
                "amount": booking_data.booking_amount or (booking_data.deal_amount * 0.10),
                "payer": "Customer",
                "status": "Paid" if booking_data.booking_amount else "Pending",
                "due_date": datetime.now()
            },
            {
                "milestone": "Allotment",
                "amount": booking_data.deal_amount * 0.25,
                "payer": "Customer",
                "status": "Pending",
                "due_date": datetime.now() + timedelta(days=30)
            },
            {
                "milestone": "Agreement Signing",
                "amount": booking_data.deal_amount * 0.10,
                "payer": "Customer",
                "status": "Pending",
                "due_date": datetime.now() + timedelta(days=45)
            },
            {
                "milestone": "Bank Disbursement",
                "amount": booking_data.deal_amount * 0.60,
                "payer": "Bank Loan",
                "status": "Pending",
                "due_date": datetime.now() + timedelta(days=60)
            },
            {
                "milestone": "Possession",
                "amount": booking_data.deal_amount * 0.05,
                "payer": "Customer",
                "status": "Pending",
                "due_date": datetime.now() + timedelta(days=180)
            }
        ]
        
        for schedule_data in schedules:
            schedule = models.PaymentSchedule(
                booking_id=new_booking.id,
                milestone=schedule_data["milestone"],
                amount=schedule_data["amount"],
                payer=schedule_data["payer"],
                status=schedule_data["status"],
                due_date=schedule_data["due_date"]
            )
            db.add(schedule)
        
        db.commit()
        
        return {
            "success": True, 
            "id": new_booking.id, 
            "message": "Booking created successfully",
            "booking": {
                "id": new_booking.id,
                "unit_number": new_booking.unit_number,
                "status": new_booking.status
            }
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Booking creation failed: {str(e)}")

@app.post("/api/booking/upload")
async def create_booking_with_upload(
    booking_data: str = Form(...),
    cheque: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    try:
        data = json.loads(booking_data)
        
        # Create booking using the JSON data
        booking_payload = BookingCreate(**data)
        
        # Call the main booking function
        result = await create_booking(booking_payload, db)
        
        # Handle cheque upload if present
        if cheque:
            filename = f"{uuid.uuid4()}_{cheque.filename}"
            path = UPLOAD_DIR / "cheques" / filename

            async with aiofiles.open(path, "wb") as f:
                await f.write(await cheque.read())

            document = models.Document(
                booking_id=result["id"],
                type="Cheque",
                file_name=cheque.filename,
                file_path=str(path),
                file_size=path.stat().st_size,
                mime_type=cheque.content_type,
                uploaded_by=1
            )
            db.add(document)
            db.commit()
        
        return result
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/booking/{booking_id}/confirm")
async def confirm_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking.status != "PENDING":
        raise HTTPException(status_code=400, detail="Booking is not in pending state")
    
    # Update booking status
    booking.status = "CONFIRMED"
    
    # Update unit status
    unit = db.query(models.Unit).filter(models.Unit.id == booking.unit_id).first()
    if unit:
        unit.status = "Booked"
    
    db.commit()
    
    return {"success": True, "message": "Booking confirmed"}

@app.patch("/api/booking/{booking_id}/cancel")
async def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Update booking status
    booking.status = "CANCELLED"
    
    # Update unit status
    unit = db.query(models.Unit).filter(models.Unit.id == booking.unit_id).first()
    if unit:
        unit.status = "Available"
        unit.booking_id = None
    
    # Update lead status
    lead = db.query(models.Lead).filter(models.Lead.id == booking.lead_id).first()
    if lead:
        lead.status = "NEGOTIATION"
    
    db.commit()
    
    return {"success": True, "message": "Booking cancelled"}

# ----- FINANCE -----

def format_amount(amount: float) -> str:
    """Format amount in Indian numbering system"""
    if amount >= 10000000:  # 1 crore
        return f"₹{amount/10000000:.2f} Cr"
    elif amount >= 100000:  # 1 lakh
        return f"₹{amount/100000:.2f} L"
    else:
        return f"₹{amount:,.0f}"

@app.get("/api/finance/schedule/{booking_id}")
async def get_payment_schedule(booking_id: int, db: Session = Depends(get_db)):
    # Get booking
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get payment schedules
    schedules = db.query(models.PaymentSchedule)\
        .filter(models.PaymentSchedule.booking_id == booking_id)\
        .order_by(models.PaymentSchedule.due_date)\
        .all()
    
    # If no schedules, create default ones (should be created during booking)
    if not schedules:
        return {
            "schedules": [],
            "summary": {
                "total_amount": 0,
                "formatted_total": "₹0",
                "paid_amount": 0,
                "formatted_paid": "₹0",
                "pending_amount": 0,
                "formatted_pending": "₹0",
                "progress_percentage": 0,
                "booking_status": booking.status,
                "deal_amount": booking.deal_amount,
                "formatted_deal_amount": format_amount(booking.deal_amount)
            }
        }
    
    # Calculate totals
    total_amount = sum(s.amount for s in schedules)
    paid_amount = sum(s.amount for s in schedules if s.status == "Paid")
    pending_amount = total_amount - paid_amount
    
    # Prepare response
    schedule_list = []
    for schedule in schedules:
        schedule_list.append({
            "id": schedule.id,
            "milestone": schedule.milestone,
            "due_date": schedule.due_date.isoformat() if schedule.due_date else None,
            "amount": schedule.amount,
            "formatted_amount": format_amount(schedule.amount),
            "payer": schedule.payer,
            "status": schedule.status,
            "payment_date": schedule.payment_date.isoformat() if schedule.payment_date else None,
            "payment_ref": schedule.payment_ref
        })
    
    return {
        "schedules": schedule_list,
        "summary": {
            "total_amount": total_amount,
            "formatted_total": format_amount(total_amount),
            "paid_amount": paid_amount,
            "formatted_paid": format_amount(paid_amount),
            "pending_amount": pending_amount,
            "formatted_pending": format_amount(pending_amount),
            "progress_percentage": (paid_amount / total_amount * 100) if total_amount > 0 else 0,
            "booking_status": booking.status,
            "deal_amount": booking.deal_amount,
            "formatted_deal_amount": format_amount(booking.deal_amount),
            "ledger_status": "Ledger Active" if pending_amount > 0 else "Ledger Closed"
        }
    }

@app.get("/api/finance/summary/{booking_id}")
async def get_finance_summary(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get all payments for this booking
    schedules = db.query(models.PaymentSchedule)\
        .filter(models.PaymentSchedule.booking_id == booking_id)\
        .all()
    
    # Calculate totals
    total_amount = booking.deal_amount
    paid_amount = sum(s.amount for s in schedules if s.status == "Paid")
    pending_amount = total_amount - paid_amount
    
    # Get payment breakdown
    breakdown = {
        "customer_paid": sum(s.amount for s in schedules if s.status == "Paid" and s.payer == "Customer"),
        "bank_paid": sum(s.amount for s in schedules if s.status == "Paid" and s.payer == "Bank Loan"),
        "customer_pending": sum(s.amount for s in schedules if s.status == "Pending" and s.payer == "Customer"),
        "bank_pending": sum(s.amount for s in schedules if s.status == "Pending" and s.payer == "Bank Loan"),
    }
    
    return {
        "booking_id": booking_id,
        "unit_number": booking.unit_number,
        "applicant_name": booking.applicant_name,
        "deal_amount": total_amount,
        "formatted_deal_amount": format_amount(total_amount),
        "paid_amount": paid_amount,
        "formatted_paid": format_amount(paid_amount),
        "pending_amount": pending_amount,
        "formatted_pending": format_amount(pending_amount),
        "payment_breakdown": breakdown,
        "status": "Ledger Active" if pending_amount > 0 else "Ledger Closed",
        "last_payment_date": max([s.payment_date for s in schedules if s.payment_date], default=None)
    }

@app.post("/api/finance/payment")
async def record_payment(
    payment_data: PaymentRecord,
    db: Session = Depends(get_db)
):
    try:
        # Find the payment schedule
        schedule = db.query(models.PaymentSchedule)\
            .filter(
                models.PaymentSchedule.booking_id == payment_data.booking_id,
                models.PaymentSchedule.milestone == payment_data.milestone
            )\
            .first()
        
        if not schedule:
            # Create a new payment record if not found
            schedule = models.PaymentSchedule(
                booking_id=payment_data.booking_id,
                milestone=payment_data.milestone,
                amount=payment_data.amount or 0,
                payer=payment_data.payer,
                status="Paid",
                payment_ref=payment_data.payment_ref,
                payment_date=datetime.fromisoformat(payment_data.payment_date) 
                    if payment_data.payment_date else datetime.now()
            )
            db.add(schedule)
        else:
            # Update existing schedule
            schedule.status = "Paid"
            schedule.payment_date = datetime.fromisoformat(payment_data.payment_date) \
                if payment_data.payment_date else datetime.now()
            schedule.payment_ref = payment_data.payment_ref
            if payment_data.amount:
                schedule.amount = payment_data.amount
        
        db.commit()
        
        return {"success": True, "message": f"Payment recorded for {payment_data.milestone}"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to record payment: {str(e)}")

@app.post("/api/finance/schedule/{booking_id}/pay")
async def mark_payment_paid(
    booking_id: int,
    milestone: str,
    payment_ref: Optional[str] = None,
    db: Session = Depends(get_db)
):
    schedule = db.query(models.PaymentSchedule)\
        .filter(
            models.PaymentSchedule.booking_id == booking_id,
            models.PaymentSchedule.milestone == milestone
        )\
        .first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Payment schedule not found")
    
    if schedule.status == "Paid":
        raise HTTPException(status_code=400, detail="Payment already marked as paid")
    
    schedule.status = "Paid"
    schedule.payment_date = datetime.now()
    schedule.payment_ref = payment_ref
    
    db.commit()
    
    return {
        "success": True, 
        "status": "Paid",
        "message": f"Payment for {milestone} marked as paid"
    }

@app.get("/api/finance/ledger-status/{booking_id}")
async def get_ledger_status(booking_id: int, db: Session = Depends(get_db)):
    """Get whether ledger is active or closed"""
    schedules = db.query(models.PaymentSchedule)\
        .filter(models.PaymentSchedule.booking_id == booking_id)\
        .all()
    
    if not schedules:
        return {"status": "No Schedule", "message": "No payment schedule found"}
    
    total_amount = sum(s.amount for s in schedules)
    paid_amount = sum(s.amount for s in schedules if s.status == "Paid")
    pending_amount = total_amount - paid_amount
    
    if pending_amount > 0:
        return {
            "status": "Ledger Active",
            "message": f"{format_amount(pending_amount)} pending payment",
            "total_amount": total_amount,
            "formatted_total": format_amount(total_amount),
            "paid_amount": paid_amount,
            "formatted_paid": format_amount(paid_amount),
            "pending_amount": pending_amount,
            "formatted_pending": format_amount(pending_amount)
        }
    else:
        return {
            "status": "Ledger Closed",
            "message": "All payments received",
            "total_amount": total_amount,
            "formatted_total": format_amount(total_amount),
            "paid_amount": paid_amount,
            "formatted_paid": format_amount(paid_amount),
            "pending_amount": 0,
            "formatted_pending": "₹0"
        }

# ----- DOCUMENTS -----

@app.post("/api/documents/upload/kyc")
async def upload_kyc(
    file: UploadFile = File(...),
    lead_id: int = Form(...),
    doc_type: str = Form(...),
    db: Session = Depends(get_db)
):
    # Generate unique filename
    file_ext = file.filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{file_ext}"
    filepath = UPLOAD_DIR / "kyc" / filename
    
    # Save file
    async with aiofiles.open(filepath, 'wb') as buffer:
        content = await file.read()
        await buffer.write(content)
    
    # Save to database
    document = models.Document(
        lead_id=lead_id,
        type=doc_type,
        file_name=file.filename,
        file_path=str(filepath),
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by=1
    )
    
    db.add(document)
    db.commit()
    
    return {"success": True, "message": "File uploaded successfully"}

@app.post("/api/documents/upload/cheque")
async def upload_cheque(
    file: UploadFile = File(...),
    booking_id: int = Form(...),
    db: Session = Depends(get_db)
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=400,
            detail=f"Booking {booking_id} does not exist"
        )
    
    # Generate unique filename
    file_ext = file.filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{file_ext}"
    filepath = UPLOAD_DIR / "cheques" / filename
    
    # Save file
    async with aiofiles.open(filepath, 'wb') as buffer:
        content = await file.read()
        await buffer.write(content)
    
    # Save to database
    document = models.Document(
        booking_id=booking_id,
        type="Cheque",
        file_name=file.filename,
        file_path=str(filepath),
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by=1
    )
    
    db.add(document)
    db.commit()
    
    return {"success": True, "message": "Cheque uploaded successfully"}

@app.get("/api/docs/templates")
async def get_document_templates():
    templates = [
        {"id": 1, "name": "Agreement to Sale", "type": "docx"},
        {"id": 2, "name": "Cost Sheet", "type": "csv"},
        {"id": 3, "name": "Possession Letter", "type": "docx"},
        {"id": 4, "name": "HDFC Demand Letter", "type": "docx"},
        {"id": 5, "name": "SBI NOC/Demand", "type": "docx"},
        {"id": 6, "name": "Payment Receipt", "type": "pdf"}
    ]
    return templates

# ----- INTERACTIONS -----

@app.get("/api/interactions/lead/{lead_id}")
async def get_lead_interactions(lead_id: int, db: Session = Depends(get_db)):
    interactions = db.query(models.Interaction)\
        .filter(models.Interaction.lead_id == lead_id)\
        .order_by(desc(models.Interaction.created_at))\
        .all()
    
    return [
        {
            "id": interaction.id,
            "lead_id": interaction.lead_id,
            "type": interaction.type,
            "notes": interaction.notes,
            "next_followup_date": interaction.next_followup_date.isoformat() if interaction.next_followup_date else None,
            "created_at": interaction.created_at.isoformat() if interaction.created_at else None
        }
        for interaction in interactions
    ]

@app.post("/api/interactions")
async def create_interaction(interaction: InteractionCreate, db: Session = Depends(get_db)):
    new_interaction = models.Interaction(
        lead_id=interaction.lead_id,
        type=interaction.type,
        notes=interaction.notes,
        next_followup_date=datetime.fromisoformat(interaction.next_followup_date) if interaction.next_followup_date else None,
        created_by=1
    )
    
    db.add(new_interaction)
    db.commit()
    
    # Update lead's last contact
    lead = db.query(models.Lead).filter(models.Lead.id == interaction.lead_id).first()
    if lead:
        lead.last_contact = datetime.now()
        if interaction.next_followup_date:
            lead.next_followup = datetime.fromisoformat(interaction.next_followup_date)
        db.commit()
    
    return {"success": True, "message": "Interaction created"}

# ----- VISITS -----

@app.get("/api/visits/lead/{lead_id}")
async def get_lead_visits(lead_id: int, db: Session = Depends(get_db)):
    visits = db.query(models.Interaction)\
        .filter(
            models.Interaction.lead_id == lead_id,
            models.Interaction.type == "Visit"
        )\
        .order_by(desc(models.Interaction.created_at))\
        .all()
    
    return [
        {
            "id": visit.id,
            "lead_id": visit.lead_id,
            "date": visit.created_at.date().isoformat() if visit.created_at else None,
            "time": visit.created_at.time().isoformat() if visit.created_at else None,
            "type": visit.type,
            "status": "Scheduled",
            "notes": visit.notes
        }
        for visit in visits
    ]

@app.post("/api/visits")
async def create_visit(interaction: InteractionCreate, db: Session = Depends(get_db)):
    # Create as visit type
    new_visit = models.Interaction(
        lead_id=interaction.lead_id,
        type="Visit",
        notes=interaction.notes,
        next_followup_date=datetime.fromisoformat(interaction.next_followup_date) if interaction.next_followup_date else None,
        created_by=1
    )
    
    db.add(new_visit)
    db.commit()
    
    return {"success": True, "message": "Visit scheduled"}

# ----- DASHBOARD -----

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    # Get counts
    total_leads = db.query(func.count(models.Lead.id)).scalar()
    visits_count = db.query(func.count(models.Interaction.id)).filter(models.Interaction.type == "Visit").scalar()
    converted_count = db.query(func.count(models.Lead.id)).filter(models.Lead.status == "BOOKED").scalar()
    
    # Revenue from bookings
    revenue_result = db.query(func.sum(models.Booking.deal_amount))\
        .filter(models.Booking.status == "BOOKED")\
        .scalar()
    revenue = revenue_result or 0
    
    # Pipeline breakdown
    pipeline = []
    statuses = ["NEW", "IN_PROGRESS", "SITE_VISIT", "NEGOTIATION", "BOOKED", "LOST"]
    for status in statuses:
        count = db.query(func.count(models.Lead.id)).filter(models.Lead.status == status).scalar()
        pipeline.append({"status": status, "count": count})
    
    # Recent leads
    recent_leads = db.query(models.Lead)\
        .order_by(desc(models.Lead.created_at))\
        .limit(5)\
        .all()
    
    recent_leads_list = [
        {
            "id": lead.id,
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "budget": lead.budget,
            "source": lead.source,
            "status": lead.status,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "owner": None
        }
        for lead in recent_leads
    ]
    
    # Recent activity
    recent_activity = []
    interactions = db.query(models.Interaction)\
        .order_by(desc(models.Interaction.created_at))\
        .limit(10)\
        .all()
    
    for interaction in interactions:
        recent_activity.append({
            "id": interaction.id,
            "user": "System",
            "action": f"{interaction.type} added",
            "time": "Recently"
        })
    
    return {
        "total_leads": total_leads,
        "visits_count": visits_count,
        "converted_count": converted_count,
        "revenue": revenue,
        "formatted_revenue": format_amount(revenue),
        "pipeline_breakdown": pipeline,
        "recent_leads": recent_leads_list,
        "recent_activity": recent_activity,
        "upcoming_visits": [
            {"id": 1, "client": "Sneha Patil", "time": "11:00 AM", "project": "Sunrise Apt"},
            {"id": 2, "client": "Amitabh B", "time": "02:30 PM", "project": "Green Valley"}
        ]
    }

# Health check
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        # Test database connection
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Property CRM Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/auth/login",
            "/api/leads",
            "/api/booking",
            "/api/dashboard/stats"
        ]
    }

