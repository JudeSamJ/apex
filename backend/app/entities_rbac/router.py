import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from decimal import Decimal

from app.database import get_db
from app.entities_rbac.models import Entity, Department, User, Role, UserRole, OnboardingStatus, UserStatus
from app.entities_rbac.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    get_current_user_context,
    UserContext
)
router = APIRouter(prefix="/api/auth", tags=["auth"])

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    entity_id: str  # The existing company the registrant is asking to join
    requested_role_id: str
    requested_department_id: Optional[str] = None

class RegisterResponse(BaseModel):
    message: str
    user_id: str
    status: str

class PendingUserOut(BaseModel):
    id: str
    email: str
    name: str
    requested_role_id: Optional[str] = None
    requested_department_id: Optional[str] = None
    created_at: Optional[str] = None

class ApproveUserIn(BaseModel):
    role_id: str
    department_id: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None

class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_url: str

class MfaCodeIn(BaseModel):
    code: str

class MfaVerifyLoginIn(BaseModel):
    challenge_token: str
    code: str

class UserRoleOut(BaseModel):
    role_id: str
    entity_id: str
    department_id: Optional[str] = None

class UserMeOut(BaseModel):
    id: str
    email: str
    name: str
    active_entity_id: str
    roles: List[str]
    accessible_departments: Optional[List[str]] = None
    mfa_enabled: bool = False

@router.post("/register", response_model=RegisterResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """Self-registration into an EXISTING company. The account is created
    PENDING with no role/access — it cannot log in until an admin on that
    entity approves it via POST /users/{id}/approve."""
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    entity = db.query(Entity).filter(Entity.id == user_in.entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Company not found")

    role = db.query(Role).filter(Role.id == user_in.requested_role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role: {user_in.requested_role_id}")

    if user_in.requested_department_id:
        dept = db.query(Department).filter(
            Department.id == user_in.requested_department_id,
            Department.entity_id == entity.id
        ).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found for this company")

    user = User(
        name=user_in.name,
        email=user_in.email,
        entity_id=entity.id,
        password_hash=get_password_hash(user_in.password),
        status=UserStatus.PENDING.value,
        requested_role_id=user_in.requested_role_id,
        requested_department_id=user_in.requested_department_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Registration submitted. An admin at your company must approve your account before you can log in.",
        "user_id": user.id,
        "status": user.status
    }

@router.post("/token", response_model=LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending admin approval. You'll be able to sign in once an admin at your company approves it."
        )
    if user.status == UserStatus.REJECTED.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your registration request was declined. Contact your company admin for details."
        )

    if user.mfa_enabled:
        # Password check passed, but a second factor is still required —
        # issue a short-lived challenge token instead of a real access token.
        return {
            "mfa_required": True,
            "mfa_challenge_token": create_mfa_challenge_token(user.id)
        }

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def mfa_enroll(current_user: UserContext = Depends(get_current_user_context), db: Session = Depends(get_db)):
    """Start TOTP enrollment: generates and stores a new secret (MFA stays
    disabled until confirmed via /mfa/confirm with a valid code)."""
    import pyotp

    user = db.query(User).filter(User.id == current_user.user_id).first()
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    user.mfa_enabled = False
    db.commit()

    otpauth_url = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Apex Fintech")
    return {"secret": secret, "otpauth_url": otpauth_url}

@router.post("/mfa/confirm")
def mfa_confirm(body: MfaCodeIn, current_user: UserContext = Depends(get_current_user_context), db: Session = Depends(get_db)):
    """Confirm enrollment by proving the authenticator app is set up correctly."""
    import pyotp

    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Call /api/auth/mfa/enroll first")

    if not pyotp.TOTP(user.mfa_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")

    user.mfa_enabled = True
    db.commit()
    return {"mfa_enabled": True}

@router.post("/mfa/disable")
def mfa_disable(body: MfaCodeIn, current_user: UserContext = Depends(get_current_user_context), db: Session = Depends(get_db)):
    """Disable MFA — requires a valid current code so a stolen session token
    alone can't be used to turn off the second factor."""
    import pyotp

    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    if not pyotp.TOTP(user.mfa_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")

    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    return {"mfa_enabled": False}

@router.post("/mfa/verify-login", response_model=TokenResponse)
def mfa_verify_login(body: MfaVerifyLoginIn, db: Session = Depends(get_db)):
    """Second step of MFA login: exchange a challenge token + TOTP code for
    a real access token."""
    from app.rate_limit import check_rate_limit

    user_id = decode_mfa_challenge_token(body.challenge_token)
    # Cap guess attempts per challenged user, independent of the challenge
    # token's own 5-minute expiry, so a stolen challenge token can't be
    # brute-forced against all 10,000 possible 6-digit codes.
    check_rate_limit(user_id=user_id, endpoint="mfa_verify_login", limit=5, window_seconds=300)

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=401, detail="MFA is not active for this account")

    import pyotp
    if not pyotp.TOTP(user.mfa_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid code")

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserMeOut)
def get_me(current_user: UserContext = Depends(get_current_user_context), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user.user_id).first()
    return {
        "id": current_user.user_id,
        "email": current_user.email,
        "name": current_user.name,
        "active_entity_id": current_user.active_entity_id,
        "roles": current_user.roles,
        "accessible_departments": current_user.accessible_departments,
        "mfa_enabled": bool(user and user.mfa_enabled)
    }

@router.post("/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    # 1. Seed Roles
    required_roles = ["ADMIN", "MANAGER", "EMPLOYEE", "BOOKKEEPER", "AP_APPROVER"]
    for role_id in required_roles:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            db.add(Role(id=role_id, name=role_id.replace("_", " ").title()))
    db.flush()

    # 2. Seed Entities (Parent/Child)
    parent_entity = db.query(Entity).filter(Entity.name == "Apex Corporation").first()
    if not parent_entity:
        parent_entity = Entity(
            name="Apex Corporation",
            onboarding_status=OnboardingStatus.APPROVED.value
        )
        db.add(parent_entity)
        db.flush()

    child_entity = db.query(Entity).filter(Entity.name == "Apex Europe GmbH").first()
    if not child_entity:
        child_entity = Entity(
            name="Apex Europe GmbH",
            onboarding_status=OnboardingStatus.PENDING.value,
            parent_entity_id=parent_entity.id
        )
        db.add(child_entity)
        db.flush()

    # 3. Seed Departments for Apex Corporation
    departments = ["Engineering", "Sales", "Marketing", "Finance"]
    depts = {}
    for dept_name in departments:
        dept = db.query(Department).filter(
            Department.name == dept_name,
            Department.entity_id == parent_entity.id
        ).first()
        if not dept:
            dept = Department(name=dept_name, entity_id=parent_entity.id)
            db.add(dept)
            db.flush()
        depts[dept_name] = dept

    # 4. Seed Users
    users_to_create = [
        {"name": "Alice Admin", "email": "admin@apex.com", "role": "ADMIN", "dept": None},
        {"name": "Bob Manager", "email": "manager@apex.com", "role": "MANAGER", "dept": "Engineering"},
        {"name": "Charlie Employee", "email": "employee@apex.com", "role": "EMPLOYEE", "dept": "Engineering"},
        {"name": "Diane Bookkeeper", "email": "bookkeeper@apex.com", "role": "BOOKKEEPER", "dept": None},
    ]

    seeded_users = []
    for u_info in users_to_create:
        user = db.query(User).filter(User.email == u_info["email"]).first()
        if not user:
            user = User(
                name=u_info["name"],
                email=u_info["email"],
                entity_id=parent_entity.id,
                password_hash=get_password_hash("password123")
            )
            db.add(user)
            db.flush()
            
            # Map role
            dept_id = depts[u_info["dept"]].id if u_info["dept"] else None
            user_role = UserRole(
                user_id=user.id,
                role_id=u_info["role"],
                entity_id=parent_entity.id,
                department_id=dept_id
            )
            db.add(user_role)
            db.flush()

            # Also map Charlie Employee as Employee in child entity (GmbH) for testing
            if u_info["email"] == "employee@apex.com":
                ur_child = UserRole(
                    user_id=user.id,
                    role_id="EMPLOYEE",
                    entity_id=child_entity.id
                )
                db.add(ur_child)
                db.flush()

        seeded_users.append({
            "name": u_info["name"],
            "email": u_info["email"],
            "role": u_info["role"],
            "dept": u_info["dept"]
        })

    # Seed dynamic approval rules for the main parent entity
    from app.approvals.models import ApprovalRule
    
    rule_card = db.query(ApprovalRule).filter(
        ApprovalRule.entity_id == parent_entity.id,
        ApprovalRule.applies_to == "CARD_REQUEST"
    ).first()
    if not rule_card:
        db.add(ApprovalRule(
            entity_id=parent_entity.id,
            applies_to="CARD_REQUEST",
            min_amount=Decimal("2000.00"),
            required_steps=["MANAGER", "ADMIN"]
        ))

    rule_bill = db.query(ApprovalRule).filter(
        ApprovalRule.entity_id == parent_entity.id,
        ApprovalRule.applies_to == "BILL"
    ).first()
    if not rule_bill:
        db.add(ApprovalRule(
            entity_id=parent_entity.id,
            applies_to="BILL",
            min_amount=Decimal("1000.00"),
            required_steps=["ADMIN"]
        ))

    db.commit()
    return {
        "message": "Demo data seeded successfully",
        "parent_entity_id": parent_entity.id,
        "child_entity_id": child_entity.id,
        "users": seeded_users
    }

class EntityOut(BaseModel):
    id: str
    name: str
    onboarding_status: str
    parent_entity_id: Optional[str] = None

class DepartmentOut(BaseModel):
    id: str
    entity_id: str
    name: str

@router.get("/entities", response_model=List[EntityOut])
def list_entities(db: Session = Depends(get_db)):
    return db.query(Entity).all()

@router.get("/departments", response_model=List[DepartmentOut])
def list_departments(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    # Returns departments for the active entity
    return db.query(Department).filter(Department.entity_id == current_user.active_entity_id).all()

@router.post("/entities/{entity_id}/status")
def update_entity_status(
    entity_id: str,
    status: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can update onboarding status")
    
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
        
    if status not in [OnboardingStatus.APPROVED.value, OnboardingStatus.PENDING.value, OnboardingStatus.SUSPENDED.value]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    entity.onboarding_status = status
    db.commit()
    return {"message": "Entity status updated successfully", "entity_id": entity_id, "status": status}

@router.get("/entities/{entity_id}/departments", response_model=List[DepartmentOut])
def list_departments_for_entity(entity_id: str, db: Session = Depends(get_db)):
    """Public (pre-login) department listing for a specific company, used by
    the registration form's department picker."""
    return db.query(Department).filter(Department.entity_id == entity_id).all()

@router.get("/pending-users", response_model=List[PendingUserOut])
def list_pending_users(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can view pending registrations")

    rows = db.query(User).filter(
        User.entity_id == current_user.active_entity_id,
        User.status == UserStatus.PENDING.value
    ).order_by(User.created_at.asc()).all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "requested_role_id": u.requested_role_id,
            "requested_department_id": u.requested_department_id,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in rows
    ]

@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    body: ApproveUserIn,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can approve registrations")

    user = db.query(User).filter(
        User.id == user_id,
        User.entity_id == current_user.active_entity_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Pending user not found")
    if user.status != UserStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"User is already {user.status}, not PENDING")

    role = db.query(Role).filter(Role.id == body.role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role: {body.role_id}")

    if body.department_id:
        dept = db.query(Department).filter(
            Department.id == body.department_id,
            Department.entity_id == current_user.active_entity_id
        ).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found for this company")

    db.add(UserRole(
        user_id=user.id,
        role_id=body.role_id,
        entity_id=current_user.active_entity_id,
        department_id=body.department_id
    ))
    user.status = UserStatus.ACTIVE.value
    db.commit()
    return {"message": f"{user.email} approved as {body.role_id}.", "user_id": user.id, "status": user.status}

@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can reject registrations")

    user = db.query(User).filter(
        User.id == user_id,
        User.entity_id == current_user.active_entity_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Pending user not found")
    if user.status != UserStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"User is already {user.status}, not PENDING")

    user.status = UserStatus.REJECTED.value
    db.commit()
    return {"message": f"{user.email} rejected.", "user_id": user.id, "status": user.status}

