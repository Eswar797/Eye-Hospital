#!/usr/bin/env python3
"""
SQLite database initialization script for Eye Hospital Patient Management System
"""

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_sqlite import Base, User, Room, UserRole
from auth import get_password_hash
from datetime import datetime

def init_database():
    """Initialize SQLite database with tables and initial data"""
    
    # Database URL
    DATABASE_URL = "sqlite:///./eye_hospital.db"
    
    # Create engine
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    
    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[OK] Database tables created")
    
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Create initial users
        print("Creating initial users...")
        
        # Check if admin user already exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@eyehospital.com",
                hashed_password=get_password_hash("admin123"),
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin_user)
            print("[OK] Admin user created (admin/admin123)")
        else:
            print("[OK] Admin user already exists")
        
        # Check if registration user exists
        reg_user = db.query(User).filter(User.username == "reg").first()
        if not reg_user:
            reg_user = User(
                username="reg",
                email="registration@eyehospital.com",
                hashed_password=get_password_hash("reg123"),
                role=UserRole.REGISTRATION,
                is_active=True
            )
            db.add(reg_user)
            print("[OK] Registration user created (reg/reg123)")
        else:
            print("[OK] Registration user already exists")
        
        # Check if nursing user exists
        nurse_user = db.query(User).filter(User.username == "nurse").first()
        if not nurse_user:
            nurse_user = User(
                username="nurse",
                email="nursing@eyehospital.com",
                hashed_password=get_password_hash("nurse123"),
                role=UserRole.NURSING,
                is_active=True
            )
            db.add(nurse_user)
            print("[OK] Nursing user created (nurse/nurse123)")
        else:
            print("[OK] Nursing user already exists")
        
        # Create initial rooms
        print("Creating initial rooms...")
        
        rooms_data = [
            {"room_number": "10", "room_name": "Vision Room", "room_type": "vision"},
            {"room_number": "1", "room_name": "OPD 1", "room_type": "opd"},
            {"room_number": "2", "room_name": "OPD 2", "room_type": "opd"},
            {"room_number": "3", "room_name": "OPD 3", "room_type": "opd"},
            {"room_number": "6", "room_name": "Refraction Room 1", "room_type": "refraction"},
            {"room_number": "7", "room_name": "Refraction Room 2", "room_type": "refraction"},
            {"room_number": "5", "room_name": "Retina Lab", "room_type": "retina"},
            {"room_number": "8", "room_name": "Biometry Room", "room_type": "biometry"},
        ]
        
        for room_data in rooms_data:
            existing_room = db.query(Room).filter(Room.room_number == room_data["room_number"]).first()
            if not existing_room:
                room = Room(
                    room_number=room_data["room_number"],
                    room_name=room_data["room_name"],
                    room_type=room_data["room_type"],
                    is_active=True
                )
                db.add(room)
                print(f"[OK] Room {room_data['room_number']} created")
            else:
                print(f"[OK] Room {room_data['room_number']} already exists")
        
        # Commit all changes
        db.commit()
        print("[OK] Database initialization completed successfully")
        
    except Exception as e:
        print(f"[ERROR] Error during initialization: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    print("Eye Hospital SQLite Database Initialization")
    print("=" * 45)
    init_database()

