from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from database_sqlite import get_db, Patient, Queue, PatientStatus, OPDType, PatientFlow
from auth import get_current_active_user, User, require_role, UserRole
from websocket_manager import broadcast_queue_update, broadcast_patient_status_update, broadcast_display_update
import asyncio

router = APIRouter()

# Pydantic models
class PatientCreate(BaseModel):
    name: str
    age: int
    phone: Optional[str] = None

class PatientUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    current_status: Optional[PatientStatus] = None
    allocated_opd: Optional[OPDType] = None
    current_room: Optional[str] = None
    is_dilated: Optional[bool] = None
    referred_from: Optional[str] = None
    referred_to: Optional[str] = None

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

class QueueResponse(BaseModel):
    id: int
    patient_id: int
    token_number: str
    patient_name: str
    position: int
    status: PatientStatus
    registration_time: datetime
    is_dilated: bool

    class Config:
        from_attributes = True

# Helper function to generate token number
def generate_token_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    last_token = db.query(Patient).filter(
        Patient.token_number.like(f"{today}%")
    ).order_by(Patient.id.desc()).first()
    
    if last_token:
        last_number = int(last_token.token_number.split('-')[-1])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"{today}-{new_number:04d}"

@router.post("/register", response_model=PatientResponse)
async def register_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REGISTRATION))
):
    # Generate unique token number
    token_number = generate_token_number(db)
    
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
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=db_patient.id,
        to_room="registration",
        status=PatientStatus.PENDING
    )
    db.add(flow_entry)
    db.commit()
    
    return db_patient

@router.post("/{patient_id}/allocate-opd")
async def allocate_opd(
    patient_id: int,
    opd_type: OPDType,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REGISTRATION))
):
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
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room="registration",
        to_room=f"opd_{opd_type.value}",
        status=PatientStatus.PENDING
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    await broadcast_queue_update(opd_type, db)
    await broadcast_display_update()
    
    return {"message": f"Patient allocated to {opd_type.value}", "queue_position": max_position + 1}

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@router.put("/{patient_id}/status")
async def update_patient_status(
    patient_id: int,
    status: PatientStatus,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    old_status = patient.current_status
    patient.current_status = status
    
    # Handle special cases
    if status == PatientStatus.DILATED:
        patient.is_dilated = True
        patient.dilation_time = datetime.utcnow()
    elif status == PatientStatus.END_VISIT:
        patient.completed_at = datetime.utcnow()
        # Remove from queue
        db.query(Queue).filter(
            Queue.patient_id == patient_id,
            Queue.opd_type == patient.allocated_opd
        ).delete()
    
    # Update queue status
    queue_entry = db.query(Queue).filter(
        Queue.patient_id == patient_id,
        Queue.opd_type == patient.allocated_opd
    ).first()
    
    if queue_entry:
        queue_entry.status = status
        queue_entry.updated_at = datetime.utcnow()
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room=patient.current_room,
        status=status,
        notes=notes
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    if patient.allocated_opd:
        await broadcast_queue_update(patient.allocated_opd, db)
    await broadcast_patient_status_update(patient_id, status, db)
    await broadcast_display_update()
    
    return {"message": f"Patient status updated to {status}"}

@router.post("/{patient_id}/refer")
async def refer_patient(
    patient_id: int,
    to_opd: OPDType,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    from_opd = patient.allocated_opd
    patient.referred_from = from_opd.value if from_opd else None
    patient.referred_to = to_opd.value
    patient.current_status = PatientStatus.REFERRED
    
    # Remove from current OPD queue
    if from_opd:
        db.query(Queue).filter(
            Queue.patient_id == patient_id,
            Queue.opd_type == from_opd
        ).delete()
    
    # Add to new OPD queue
    max_position = db.query(func.max(Queue.position)).filter(
        Queue.opd_type == to_opd
    ).scalar() or 0
    
    queue_entry = Queue(
        opd_type=to_opd,
        patient_id=patient_id,
        position=max_position + 1,
        status=PatientStatus.PENDING
    )
    db.add(queue_entry)
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room=f"opd_{from_opd.value}" if from_opd else None,
        to_room=f"opd_{to_opd.value}",
        status=PatientStatus.REFERRED,
        notes=f"Referred from {from_opd.value} to {to_opd.value}"
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    if from_opd:
        await broadcast_queue_update(from_opd, db)
    await broadcast_queue_update(to_opd, db)
    await broadcast_patient_status_update(patient_id, PatientStatus.REFERRED, db)
    await broadcast_display_update()
    
    return {"message": f"Patient referred from {from_opd.value if from_opd else 'registration'} to {to_opd.value}"}

@router.get("/", response_model=List[PatientResponse])
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
