from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import uuid
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = "mysql+pymysql://root:@localhost/licensekeytest"  # เปลี่ยนเป็น mysql+pymysql://user:password@localhost/dbname ถ้าต้องการใช้ MySQL

engine = create_engine(DATABASE_URL) 
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # หรือเฉพาะ origin เช่น ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class ActiveSystem(Base):
    __tablename__ = "active_system"
    id = Column(Integer, primary_key=True, index=True)
    system_name = Column(String, unique=True, nullable=False)

class LicenseKey(Base):
    __tablename__ = "license_key"
    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String, unique=True, nullable=False)
    active_system_id = Column(Integer, ForeignKey("active_system.id"), nullable=True)
    create_at = Column(TIMESTAMP, server_default=func.now())

    active_system = relationship("ActiveSystem")  # join object

Base.metadata.create_all(bind=engine)

# ---------- Schemas ----------
class ActiveSystemCreate(BaseModel):
    system_name: str

class LicenseCreate(BaseModel):
    active_system_id: int

class LicenseResponse(BaseModel):
    license_key: str
    active_system: str

# ---------- APIs ----------
@app.post("/active_system")
def create_active_system(data: ActiveSystemCreate):
    db = SessionLocal()
    try:
        existing = db.query(ActiveSystem).filter(ActiveSystem.system_name == data.system_name).first()
        if existing:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"message": "Active system นี้มีการลงทะเบียนแล้ว"}
            )

        new_system = ActiveSystem(system_name=data.system_name)
        db.add(new_system)
        db.commit()
        db.refresh(new_system)
        return {"system_name": new_system.system_name}
    finally:
        db.close()

@app.get("/active_system")
def list_active_systems():
    db = SessionLocal()
    try:
        systems = db.query(ActiveSystem).all()
        return [{"id": s.id, "system_name": s.system_name} for s in systems]
    finally:
        db.close()

@app.post("/generate", response_model=LicenseResponse)
def generate_license(data: LicenseCreate):
    db = SessionLocal()
    try:
        active_system = db.query(ActiveSystem).filter(ActiveSystem.id == data.active_system_id).first()
        if not active_system:
            raise HTTPException(status_code=404, detail="Active system not found.")

        license_key = str(uuid.uuid4())
        new_license = LicenseKey(license_key=license_key, active_system_id=active_system.id)
        db.add(new_license)
        db.commit()
        db.refresh(new_license)
        return {
            "license_key": new_license.license_key,
            "active_system": active_system.system_name
        }
    finally:
        db.close()

@app.get("/licenses")
def list_licenses():
    db = SessionLocal()
    try:
        licenses = db.query(LicenseKey).all()
        return [{
            "license_key": l.license_key,
            "active_system": l.active_system.system_name if l.active_system else None,
            "create_at": l.create_at
        } for l in licenses]
    finally:
        db.close()