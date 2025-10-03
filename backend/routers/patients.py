from fastapi import APIRouter, Depends, HTTPException, status, Query
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
class AllocateOPDRequest(BaseModel):
    opd_type: OPDType

class ReferPatientRequest(BaseModel):
    to_opd: OPDType

class ReferredPatientResponse(BaseModel):
    id: int
    token_number: str
    name: str
    age: int
    registration_time: datetime
    from_opd: Optional[str]
    to_opd: Optional[str]

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
        phone=patient_data.phone,
        registration_time=datetime.now()
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

# Place static route BEFORE any dynamic /{patient_id} routes to avoid conflicts
@router.get("/referred", response_model=List[ReferredPatientResponse])
async def list_referred_patients(
    from_opd: Optional[str] = Query(default=None, alias="from_opd"),
    to_opd: Optional[str] = Query(default=None, alias="to_opd"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(Patient).filter(Patient.current_status == PatientStatus.REFERRED)

    valid_opds = {opd.value for opd in OPDType}
    if from_opd and from_opd in valid_opds:
        query = query.filter(Patient.referred_from == from_opd)
    if to_opd and to_opd in valid_opds:
        query = query.filter(Patient.referred_to == to_opd)

    patients = query.order_by(Patient.registration_time.asc()).all()

    return [
        ReferredPatientResponse(
            id=p.id,
            token_number=p.token_number,
            name=p.name,
            age=p.age,
            registration_time=p.registration_time,
            from_opd=p.referred_from,
            to_opd=p.referred_to,
        ) for p in patients
    ]

@router.post("/{patient_id}/allocate-opd")
async def allocate_opd(
    patient_id: int,
    payload: AllocateOPDRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REGISTRATION))
):
    print("patients.py: allocate_opd")
    opd_type = payload.opd_type
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
    elif status == PatientStatus.COMPLETED:
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
    payload: ReferPatientRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    to_opd = payload.to_opd
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    from_opd = patient.allocated_opd
    patient.referred_from = from_opd.value if from_opd else None
    patient.referred_to = to_opd.value
    patient.current_status = PatientStatus.REFERRED

    # Keep patient in current OPD queue but mark their queue status as REFERRED
    if from_opd:
        queue_entry = db.query(Queue).filter(
            Queue.patient_id == patient_id,
            Queue.opd_type == from_opd
        ).first()
        if queue_entry:
            queue_entry.status = PatientStatus.REFERRED

    # Ensure patient is ALSO present in the destination OPD queue with REFERRED status
    # Create only if not already present
    to_queue_entry = db.query(Queue).filter(
        Queue.patient_id == patient_id,
        Queue.opd_type == to_opd
    ).first()
    if not to_queue_entry:
        max_position_to = db.query(func.max(Queue.position)).filter(
            Queue.opd_type == to_opd
        ).scalar() or 0
        to_queue_entry = Queue(
            opd_type=to_opd,
            patient_id=patient_id,
            position=max_position_to + 1,
            status=PatientStatus.REFERRED
        )
        db.add(to_queue_entry)
    else:
        # If exists, ensure status is REFERRED
        to_queue_entry.status = PatientStatus.REFERRED

    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room=f"opd_{from_opd.value}" if from_opd else None,
        to_room=f"opd_{to_opd.value}",
        status=PatientStatus.REFERRED,
        notes=f"Referred from {from_opd.value if from_opd else 'registration'} to {to_opd.value}"
    )
    db.add(flow_entry)
    db.commit()

    # Broadcast updates (update both OPD queues and global display)
    if from_opd:
        await broadcast_queue_update(from_opd, db)
    await broadcast_queue_update(to_opd, db)
    await broadcast_patient_status_update(patient_id, PatientStatus.REFERRED, db)
    await broadcast_display_update()

    return {"message": f"Patient referred to {to_opd.value} and present in both queues as referred"}




    
'''
@router.get("/referred", response_model=List[ReferredPatientResponse])
async def list_referred_patients(
    from_opd: Optional[str] = Query(default=None, alias="from_opd"),
    to_opd: Optional[str] = Query(default=None, alias="to_opd"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    print("patients.py: list_referred_patients")
    print(from_opd)
    print(to_opd)
    query = db.query(Patient).filter(Patient.current_status == PatientStatus.REFERRED)

    valid_opds = {opd.value for opd in OPDType}
    if from_opd and from_opd in valid_opds:
        query = query.filter(Patient.referred_from == from_opd)
    if to_opd and to_opd in valid_opds:
        query = query.filter(Patient.referred_to == to_opd)

    patients = query.order_by(Patient.registration_time.asc()).all()

    # Map to response with from_opd and to_opd strings
    result = []
    for p in patients:
        result.append(ReferredPatientResponse(
            id=p.id,
            token_number=p.token_number,
            name=p.name,
            age=p.age,
            registration_time=p.registration_time,
            from_opd=p.referred_from,
            to_opd=p.referred_to,
        ))

    return result
'''

@router.get("/", response_model=List[PatientResponse])
async def get_patients(
    skip: int = 0,
    limit: int = 100,
    status: Optional[PatientStatus] = None,
    latest: Optional[bool] = Query(False), # New parameter to fetch latest patients
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    print("get_patients")
    query = db.query(Patient)
    print("status", status)
    print("latest", latest)
    
    if status:
        query = query.filter(Patient.current_status == status)
    
    if latest:
        # If 'latest' is true, order by registration time descending and limit to 5
        patients = query.order_by(Patient.registration_time.desc()).limit(5).all()
        print("Fetching latest 5 patients.")
    else:
        # Otherwise, apply skip and limit for general pagination
        patients = query.order_by(Patient.registration_time.desc()).offset(skip).limit(limit).all()
        print(f"Fetching patients with skip={skip}, limit={limit}.")
    
    for patient in patients:
        print(patient.name, patient.registration_time)
    return patients



@router.post("/{patient_id}/endvisit")
async def end_patient_visit(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Store current OPD and room for broadcasting and logging before clearing them
    opd_to_update = patient.allocated_opd
    print("opd_to_update", opd_to_update)
    from_room = patient.current_room
    print("from_room", from_room)

    # Update patient status and details
    patient.current_status = PatientStatus.COMPLETED
    patient.status = PatientStatus.COMPLETED
    patient.completed_at = datetime.now()
    patient.current_room = None # Patient is no longer in any active room
    patient.allocated_opd = None # Patient is no longer allocated to an OPD
    patient.referred_from = None # Clear referral status
    patient.referred_to = None # Clear referral status

    # Remove patient from ALL queue entries (they should not appear in any queue after completion)
    queue_entries = db.query(Queue).filter(Queue.patient_id == patient_id).all()
    print("queue_entries to remove", queue_entries)
    for queue_entry in queue_entries:
        db.delete(queue_entry)

    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room=from_room,
        to_room="completed",
        status=PatientStatus.COMPLETED,
        notes="Patient visit completed"
    )
    db.add(flow_entry)
    db.commit()
    print("committed")
    db.refresh(patient) # Refresh patient object to reflect latest DB state

    # Broadcast updates
    
    if opd_to_update:
        await broadcast_queue_update(opd_to_update, db) # Update the queue they just left
    await broadcast_patient_status_update(patient_id, PatientStatus.COMPLETED, db)
    await broadcast_display_update()

    return {"message": f"Patient {patient.token_number} visit completed."}