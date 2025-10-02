from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from database_sqlite import get_db, Patient, Queue, PatientStatus, OPDType, PatientFlow
from auth import get_current_active_user, User, require_role, UserRole
from websocket_manager import broadcast_queue_update, broadcast_patient_status_update, broadcast_display_update

router = APIRouter()

# Pydantic models
class QueueResponse(BaseModel):
    id: int
    patient_id: int
    token_number: str
    patient_name: str
    position: int
    status: PatientStatus
    registration_time: datetime
    is_dilated: bool
    age: int
    phone: Optional[str]

    class Config:
        from_attributes = True

class OPDStats(BaseModel):
    opd_type: OPDType
    total_patients: int
    pending_patients: int
    in_opd_patients: int
    dilated_patients: int
    referred_patients: int
    completed_today: int
    avg_waiting_time: Optional[float]

@router.get("/{opd_type}/queue", response_model=List[QueueResponse])
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
        queue_data.append(QueueResponse(
            id=entry.id,
            patient_id=entry.patient_id,
            token_number=entry.patient.token_number,
            patient_name=entry.patient.name,
            position=entry.position,
            status=entry.status,
            registration_time=entry.patient.registration_time,
            is_dilated=entry.patient.is_dilated,
            age=entry.patient.age,
            phone=entry.patient.phone
        ))
    
    return queue_data

@router.post("/{opd_type}/call-next")
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
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=next_patient.patient_id,
        from_room="waiting_area",
        to_room=f"opd_{opd_type.value}",
        status=PatientStatus.IN_OPD
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    await broadcast_queue_update(opd_type, db)
    await broadcast_patient_status_update(next_patient.patient_id, PatientStatus.IN_OPD, db)
    await broadcast_display_update()
    
    return {
        "message": f"Patient {next_patient.patient.token_number} called",
        "patient": {
            "id": next_patient.patient_id,
            "token_number": next_patient.patient.token_number,
            "name": next_patient.patient.name,
            "position": next_patient.position
        }
    }

@router.post("/{opd_type}/dilate-patient/{patient_id}")
async def dilate_patient(
    opd_type: OPDType,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.allocated_opd != opd_type:
        raise HTTPException(status_code=400, detail="Patient not in this OPD")
    
    # Update patient status
    patient.current_status = PatientStatus.DILATED
    patient.is_dilated = True
    patient.dilation_time = datetime.utcnow()
    
    # Update queue status
    queue_entry = db.query(Queue).filter(
        Queue.patient_id == patient_id,
        Queue.opd_type == opd_type
    ).first()
    
    if queue_entry:
        queue_entry.status = PatientStatus.DILATED
        queue_entry.updated_at = datetime.utcnow()
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room=f"opd_{opd_type.value}",
        to_room="dilation_area",
        status=PatientStatus.DILATED,
        notes="Patient given dilation drops, waiting 30-40 minutes"
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    await broadcast_queue_update(opd_type, db)
    await broadcast_patient_status_update(patient_id, PatientStatus.DILATED, db)
    await broadcast_display_update()
    
    return {"message": f"Patient {patient.token_number} marked for dilation"}

@router.post("/{opd_type}/return-dilated/{patient_id}")
async def return_dilated_patient(
    opd_type: OPDType,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.NURSING))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if not patient.is_dilated:
        raise HTTPException(status_code=400, detail="Patient is not dilated")
    
    # Check if dilation time has passed (30-40 minutes)
    if patient.dilation_time:
        time_since_dilation = datetime.utcnow() - patient.dilation_time
        if time_since_dilation < timedelta(minutes=30):
            remaining_time = 30 - int(time_since_dilation.total_seconds() / 60)
            raise HTTPException(
                status_code=400, 
                detail=f"Dilation time not complete. Please wait {remaining_time} more minutes"
            )
    
    # Update patient status back to IN_OPD
    patient.current_status = PatientStatus.IN_OPD
    patient.current_room = f"opd_{opd_type.value}"
    
    # Update queue status
    queue_entry = db.query(Queue).filter(
        Queue.patient_id == patient_id,
        Queue.opd_type == opd_type
    ).first()
    
    if queue_entry:
        queue_entry.status = PatientStatus.IN_OPD
        queue_entry.updated_at = datetime.utcnow()
    
    # Log patient flow
    flow_entry = PatientFlow(
        patient_id=patient_id,
        from_room="dilation_area",
        to_room=f"opd_{opd_type.value}",
        status=PatientStatus.IN_OPD,
        notes="Patient returned from dilation"
    )
    db.add(flow_entry)
    db.commit()
    
    # Broadcast updates
    await broadcast_queue_update(opd_type, db)
    await broadcast_patient_status_update(patient_id, PatientStatus.IN_OPD, db)
    await broadcast_display_update()
    
    return {"message": f"Patient {patient.token_number} returned from dilation"}

@router.get("/{opd_type}/stats", response_model=OPDStats)
async def get_opd_stats(
    opd_type: OPDType,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    today = datetime.utcnow().date()
    
    # Get queue statistics
    total_patients = db.query(Queue).filter(Queue.opd_type == opd_type).count()
    pending_patients = db.query(Queue).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.PENDING
    ).count()
    in_opd_patients = db.query(Queue).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.IN_OPD
    ).count()
    dilated_patients = db.query(Queue).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.DILATED
    ).count()
    referred_patients = db.query(Queue).filter(
        Queue.opd_type == opd_type,
        Queue.status == PatientStatus.REFERRED
    ).count()
    
    # Get completed patients today
    completed_today = db.query(Patient).filter(
        Patient.allocated_opd == opd_type,
        Patient.current_status == PatientStatus.END_VISIT,
        func.date(Patient.completed_at) == today
    ).count()
    
    # Calculate average waiting time (simplified)
    avg_waiting_time = None
    completed_patients = db.query(Patient).filter(
        Patient.allocated_opd == opd_type,
        Patient.current_status == PatientStatus.END_VISIT,
        func.date(Patient.completed_at) == today
    ).all()
    
    if completed_patients:
        total_waiting_time = 0
        for patient in completed_patients:
            if patient.completed_at:
                waiting_time = (patient.completed_at - patient.registration_time).total_seconds() / 60
                total_waiting_time += waiting_time
        avg_waiting_time = total_waiting_time / len(completed_patients)
    
    return OPDStats(
        opd_type=opd_type,
        total_patients=total_patients,
        pending_patients=pending_patients,
        in_opd_patients=in_opd_patients,
        dilated_patients=dilated_patients,
        referred_patients=referred_patients,
        completed_today=completed_today,
        avg_waiting_time=avg_waiting_time
    )

@router.get("/stats/all", response_model=List[OPDStats])
async def get_all_opd_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    stats = []
    for opd_type in OPDType:
        opd_stats = await get_opd_stats(opd_type, db, current_user)
        stats.append(opd_stats)
    
    return stats
