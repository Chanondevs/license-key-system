from fastapi import FastAPI, HTTPException, status, Depends, Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
import uuid

# Database URL (แก้ตามของคุณ)
DATABASE_URL = "mysql+pymysql://root:mfxZlMwcZEcGgKepqMxeRddLOWWifDwJ@crossover.proxy.rlwy.net:19484/railway"

# SQLAlchemy setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

# FastAPI app
app = FastAPI()

# CORS middleware (ปรับ origin ตามต้องการ)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # หรือใส่เฉพาะ domain เช่น ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = "MCCODETEAM"  # เปลี่ยนเป็น key ของคุณเอง
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 วัน

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ------------------- Models -------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

class ActiveSystem(Base):
    __tablename__ = "active_system"
    id = Column(Integer, primary_key=True, index=True)
    system_name = Column(String(255), unique=True, nullable=False)

class LicenseKey(Base):
    __tablename__ = "license_key"
    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String(255), unique=True, nullable=False)
    active_system_id = Column(Integer, ForeignKey("active_system.id"), nullable=True)
    create_at = Column(TIMESTAMP, server_default=func.now())

    active_system = relationship("ActiveSystem")

class LicenseUsageLog(Base):
    __tablename__ = "license_usage_log"
    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String(255), nullable=False, index=True)
    active_system_id = Column(Integer, ForeignKey("active_system.id"), nullable=True)
    used_at = Column(TIMESTAMP, server_default=func.now())
    ip_address = Column(String(45), nullable=True)  # รองรับ IPv6
    details = Column(String, nullable=True)

    active_system = relationship("ActiveSystem")

Base.metadata.create_all(bind=engine)

# ------------------- Schemas -------------------
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ActiveSystemCreate(BaseModel):
    system_name: str

class LicenseCreate(BaseModel):
    active_system_id: int

class LicenseResponse(BaseModel):
    license_key: str
    active_system: str

class LicenseCheckRequest(BaseModel):
    license_key: str

class LicenseCheckResponse(BaseModel):
    valid: bool
    message: str

# ------------------- Utility Functions -------------------
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ไม่ถูกต้องหรือหมดอายุ",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    db = SessionLocal()
    user = get_user(db, username=username)
    db.close()
    if user is None:
        raise credentials_exception
    return user

# Dependency สำหรับดึง db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------- API Routes -------------------

@app.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user(db, user.username)
    if existing_user:
        return JSONResponse(status_code=400, content={"message": "Username นี้ถูกใช้แล้ว"})
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "สมัครสมาชิกสำเร็จ"}

@app.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username หรือ รหัสผ่านไม่ถูกต้อง")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username}

@app.post("/active_system")
def create_active_system(
    data: ActiveSystemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
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

@app.get("/active_system")
def list_active_systems(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    systems = db.query(ActiveSystem).all()
    return [{"id": s.id, "system_name": s.system_name} for s in systems]

@app.post("/generate", response_model=LicenseResponse)
def generate_license(
    data: LicenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
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

@app.get("/licenses")
def list_licenses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    licenses = db.query(LicenseKey).all()
    return [{
        "license_key": l.license_key,
        "active_system": l.active_system.system_name if l.active_system else None,
        "create_at": l.create_at
    } for l in licenses]

# API สำหรับเช็ค license key และบันทึก log (ไม่ต้องใช้ token)
@app.post("/check_license", response_model=LicenseCheckResponse)
def check_license(
    data: LicenseCheckRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    ip_address = None
    if request:
        ip_address = request.client.host
        xff = request.headers.get("x-forwarded-for")
        if xff:
            ip_address = xff.split(",")[0].strip()

    license_record = db.query(LicenseKey).filter(LicenseKey.license_key == data.license_key).first()

    if not license_record:
        log = LicenseUsageLog(
            license_key=data.license_key,
            active_system_id=None,
            ip_address=ip_address,
            details="License key not found"
        )
        db.add(log)
        db.commit()
        return {"valid": False, "message": "License key ไม่ถูกต้อง"}

    log = LicenseUsageLog(
        license_key=license_record.license_key,
        active_system_id=license_record.active_system_id,
        ip_address=ip_address,
        details="License key valid"
    )
    db.add(log)
    db.commit()

    return {"valid": True, "message": "License key ถูกต้อง"}

@app.get("/license_info/{license_key}")
def license_info(license_key: str, db: Session = Depends(get_db)):
    license_record = db.query(LicenseKey).filter(LicenseKey.license_key == license_key).first()
    if not license_record:
        raise HTTPException(status_code=404, detail="License key ไม่ถูกต้อง")

    return {
        "license_key": license_record.license_key,
        "active_system_id": license_record.active_system_id,
        "active_system_name": license_record.active_system.system_name if license_record.active_system else None,
        "create_at": license_record.create_at,
    }