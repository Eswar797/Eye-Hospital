from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
import os

from database_sqlite import engine, Base, get_db, User, Room, Patient, Queue, PatientStatus, OPDType, PatientFlow, UserRole
from auth import get_password_hash, verify_password, create_access_token, get_current_active_user, require_role

load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Eye Hospital Patient Management System",
    description="Real-time queue and patient flow management system",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class PatientCreate(BaseModel):
    name: str
    age: int
    phone: Optional[str] = None

class PatientResponse(BaseModel):
    id: int
    token_number: str
    name: str
    age: int
    phone: Optional[str]
    registration_time: datetime
    current_status: PatientStatus
    allocated_opd: Optional[OPDType]
    current_room: Optional[str]
    is_dilated: bool
    dilation_time: Optional[datetime]
    referred_from: Optional[str]
    referred_to: Optional[str]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

# Authentication endpoints
@app.post("/api/auth/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_credentials.username).first()
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# Patient endpoints
@app.post("/api/patients/register", response_model=PatientResponse)
async def register_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REGISTRATION))
):
    # Generate unique token number
    today = datetime.now().strftime("%Y%m%d")
    last_token = db.query(Patient).filter(
        Patient.token_number.like(f"{today}%")
    ).order_by(Patient.id.desc()).first()
    
    if last_token:
        last_number = int(last_token.token_number.split('-')[-1])
        new_number = last_number + 1
    else:
        new_number = 1
    
    token_number = f"{today}-{new_number:04d}"
    
    # Create patient
    db_patient = Patient(
        token_number=token_number,
        name=patient_data.name,
        age=patient_data.age,
        phone=patient_data.phone
    )
    
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    
    return db_patient

@app.get("/api/patients", response_model=List[PatientResponse])
async def get_patients(
    skip: int = 0,
    limit: int = 100,
    status: Optional[PatientStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(Patient)
    if status:
        query = query.filter(Patient.current_status == status)
    
    patients = query.offset(skip).limit(limit).all()
    return patients

class OPDAllocationRequest(BaseModel):
    opd_type: OPDType

@app.post("/api/patients/{patient_id}/allocate-opd")
async def allocate_opd(
    patient_id: int,
    request: OPDAllocationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REGISTRATION))
):
    opd_type = request.opd_type
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Update patient OPD allocation
    patient.allocated_opd = opd_type
    patient.current_room = f"opd_{opd_type.value}"
    
    # Add to OPD queue
    max_position = db.query(func.max(Queue.position)).filter(
        Queue.opd_type == opd_type
    ).scalar() or 0
    
    queue_entry = Queue(
        opd_type=opd_type,
        patient_id=patient_id,
        position=max_position + 1,
        status=PatientStatus.PENDING
    )
    
    db.add(queue_entry)
    db.commit()
    
    return {"message": f"Patient allocated to {opd_type.value}", "queue_position": max_position + 1}

# OPD endpoints
@app.get("/api/opd/{opd_type}/queue")
async def get_opd_queue(
    opd_type: OPDType,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    queue_entries = db.query(Queue).join(Patient).filter(
        Queue.opd_type == opd_type,
        Queue.status.in_([PatientStatus.PENDING, PatientStatus.IN_OPD, PatientStatus.DILATED])
    ).order_by(Queue.position).all()
    
    queue_data = []
    for entry in queue_entries:
        queue_data.append({
            "id": entry.id,
            "patient_id": entry.patient_id,
            "token_number": entry.patient.token_number,
            "patient_name": entry.patient.name,
            "position": entry.position,
            "status": entry.status,
            "registration_time": entry.patient.registration_time.isoformat(),
            "is_dilated": entry.patient.is_dilated,
            "age": entry.patient.age,
            "phone": entry.patient.phone
        })
    
    return queue_data

@app.post("/api/opd/{opd_type}/call-next")
async def call_next_patient(
    opd_type: OPDType,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    # Get next patient in queue
    next_patient = db.query(Queue).join(Patient).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.PENDING
    ).order_by(Queue.position).first()
    
    if not next_patient:
        raise HTTPException(status_code=404, detail="No patients in queue")
    
    # Update patient status to IN_OPD
    next_patient.status = PatientStatus.IN_OPD
    next_patient.patient.current_status = PatientStatus.IN_OPD
    next_patient.patient.current_room = f"opd_{opd_type.value}"
    next_patient.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": f"Patient {next_patient.patient.token_number} called",
        "patient": {
            "id": next_patient.patient_id,
            "token_number": next_patient.patient.token_number,
            "name": next_patient.patient.name,
            "position": next_patient.position
        }
    }

# Display endpoints
@app.get("/api/display/{opd_type}")
async def get_opd_display_data(
    opd_type: OPDType,
    db: Session = Depends(get_db)
):
    # Get current patient (IN_OPD status)
    current_patient_query = db.query(Queue).join(Patient).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.IN_OPD
    ).order_by(Queue.position).first()
    
    current_patient = None
    if current_patient_query:
        current_patient = {
            "position": current_patient_query.position,
            "token_number": current_patient_query.patient.token_number,
            "patient_name": current_patient_query.patient.name,
            "status": current_patient_query.status,
            "waiting_time_minutes": int((datetime.utcnow() - current_patient_query.patient.registration_time).total_seconds() / 60),
            "is_dilated": current_patient_query.patient.is_dilated
        }
    
    # Get next patients (PENDING status)
    next_patients_query = db.query(Queue).join(Patient).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.PENDING
    ).order_by(Queue.position).limit(5).all()
    
    next_patients = []
    for entry in next_patients_query:
        next_patients.append({
            "position": entry.position,
            "token_number": entry.patient.token_number,
            "patient_name": entry.patient.name,
            "status": entry.status,
            "waiting_time_minutes": int((datetime.utcnow() - entry.patient.registration_time).total_seconds() / 60),
            "is_dilated": entry.patient.is_dilated
        })
    
    # Get total patients in queue
    total_patients = db.query(Queue).filter(
        Queue.opd_type == opd_type,
        Queue.status.in_([PatientStatus.PENDING, PatientStatus.IN_OPD, PatientStatus.DILATED])
    ).count()
    
    return {
        "opd_type": opd_type,
        "current_patient": current_patient,
        "next_patients": next_patients,
        "total_patients": total_patients,
        "estimated_wait_time": len(next_patients) * 10 if next_patients else None
    }

@app.get("/api/display/all")
async def get_all_opds_display_data(db: Session = Depends(get_db)):
    opds_data = []
    
    for opd_type in OPDType:
        opd_data = await get_opd_display_data(opd_type, db)
        opds_data.append(opd_data)
    
    return {
        "opds": opds_data,
        "last_updated": datetime.utcnow().isoformat()
    }

# Admin endpoints
@app.get("/api/admin/dashboard")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    today = datetime.utcnow().date()
    
    # Get today's patient statistics
    total_patients_today = db.query(Patient).filter(
        func.date(Patient.registration_time) == today
    ).count()
    
    total_patients_pending = db.query(Patient).filter(
        Patient.current_status == PatientStatus.PENDING
    ).count()
    
    total_patients_in_opd = db.query(Patient).filter(
        Patient.current_status == PatientStatus.IN_OPD
    ).count()
    
    total_patients_dilated = db.query(Patient).filter(
        Patient.current_status == PatientStatus.DILATED
    ).count()
    
    total_patients_completed = db.query(Patient).filter(
        Patient.current_status == PatientStatus.END_VISIT,
        func.date(Patient.completed_at) == today
    ).count()
    
    # Get OPD-wise statistics
    opd_stats = []
    for opd_type in OPDType:
        opd_patients = db.query(Patient).filter(Patient.allocated_opd == opd_type).count()
        opd_pending = db.query(Queue).filter(
            Queue.opd_type == opd_type,
            Queue.status == PatientStatus.PENDING
        ).count()
        opd_in_progress = db.query(Queue).filter(
            Queue.opd_type == opd_type,
            Queue.status == PatientStatus.IN_OPD
        ).count()
        opd_completed = db.query(Patient).filter(
            Patient.allocated_opd == opd_type,
            Patient.current_status == PatientStatus.END_VISIT,
            func.date(Patient.completed_at) == today
        ).count()
        
        opd_stats.append({
            "opd_type": opd_type.value,
            "total_patients": opd_patients,
            "pending": opd_pending,
            "in_progress": opd_in_progress,
            "completed_today": opd_completed
        })
    
    return {
        "total_patients_today": total_patients_today,
        "total_patients_pending": total_patients_pending,
        "total_patients_in_opd": total_patients_in_opd,
        "total_patients_dilated": total_patients_dilated,
        "total_patients_completed": total_patients_completed,
        "opd_stats": opd_stats
    }

@app.get("/")
async def root():
    return {"message": "Eye Hospital Patient Management System API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main_clean:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
