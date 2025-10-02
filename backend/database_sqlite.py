from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import os
from dotenv import load_dotenv

load_dotenv()

# Database URL - Using SQLite for easy setup
DATABASE_URL = "sqlite:///./eye_hospital.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enums
class PatientStatus(str, enum.Enum):
    PENDING = "pending"
    IN_OPD = "in"
    END_VISIT = "end_visit"
    DILATED = "dilated"
    REFERRED = "referred"
    COME_BACK = "come_back"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    REGISTRATION = "registration"
    NURSING = "nursing"

class OPDType(str, enum.Enum):
    OPD1 = "opd1"
    OPD2 = "opd2"
    OPD3 = "opd3"

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String, unique=True, index=True, nullable=False)
    room_name = Column(String, nullable=False)
    room_type = Column(String, nullable=False)  # vision, opd, refraction, retina, biometry
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True, index=True)
    token_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    phone = Column(String)
    registration_time = Column(DateTime, default=datetime.utcnow)
    current_status = Column(SQLEnum(PatientStatus), default=PatientStatus.PENDING)
    allocated_opd = Column(SQLEnum(OPDType))
    current_room = Column(String)
    is_dilated = Column(Boolean, default=False)
    dilation_time = Column(DateTime)
    referred_from = Column(String)
    referred_to = Column(String)
    completed_at = Column(DateTime)

class Queue(Base):
    __tablename__ = "queues"
    
    id = Column(Integer, primary_key=True, index=True)
    opd_type = Column(SQLEnum(OPDType), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    position = Column(Integer, nullable=False)
    status = Column(SQLEnum(PatientStatus), default=PatientStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient", back_populates="queue_entries")

# Add relationship to Patient model
Patient.queue_entries = relationship("Queue", back_populates="patient")

class PatientFlow(Base):
    __tablename__ = "patient_flows"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    from_room = Column(String)
    to_room = Column(String)
    status = Column(SQLEnum(PatientStatus), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    notes = Column(String)
    
    patient = relationship("Patient")

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
