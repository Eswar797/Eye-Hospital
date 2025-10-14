from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import socketio
from contextlib import asynccontextmanager
import uvicorn
from dotenv import load_dotenv
import os

from database_sqlite import engine, Base
from routers import auth, patients, opd, admin, display, printing
from websocket_manager import sio

load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown

app = FastAPI(
    title="Eye Hospital Patient Management System",
    description="Real-time queue and patient flow management system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware - Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(patients.router, prefix="/api/patients", tags=["patients"])
app.include_router(opd.router, prefix="/api/opd", tags=["opd"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(display.router, prefix="/api/display", tags=["display"])
app.include_router(printing.router, prefix="/api/printing", tags=["printing"])

# Mount Socket.IO
app.mount("/socket.io", socketio.ASGIApp(sio))

@app.get("/")
async def root():
    return {"message": "Eye Hospital Patient Management System API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/test-auth")
async def test_auth():
    """Test authentication system"""
    try:
        from database_sqlite import SessionLocal, User
        from auth import verify_password, authenticate_user
        
        db = SessionLocal()
        user = db.query(User).filter(User.username == "admin").first()
        
        if not user:
            return {"error": "User not found"}
        
        # Test password verification
        password_test = verify_password("admin123", user.hashed_password)
        
        # Test authenticate_user
        auth_test = authenticate_user(db, "admin", "admin123")
        
        db.close()
        
        return {
            "user_found": True,
            "username": user.username,
            "password_verify": password_test,
            "authenticate_user": auth_test is not False,
            "status": "ok"
        }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
