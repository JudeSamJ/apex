import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from decimal import Decimal

from app.database import get_db
from app.entities_rbac.models import Entity, Department, User, Role, UserRole, OnboardingStatus
from app.entities_rbac.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user_context,
    UserContext
)
from app.kyc.client import get_didit_client
from app.screening.service import screen_subject

router = APIRouter(prefix="/api/auth", tags=["auth"])

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    entity_name: str  # Creates a new entity on signup

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

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

@router.post("/register", response_model=TokenResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    # Check duplicate
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Ensure roles exist
    required_roles = ["ADMIN", "MANAGER", "EMPLOYEE", "BOOKKEEPER", "AP_APPROVER"]
    for role_id in required_roles:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            db.add(Role(id=role_id, name=role_id.replace("_", " ").title()))
    db.commit()

    # Create Entity with pending onboarding status
    entity = Entity(
        name=user_in.entity_name,
        onboarding_status=OnboardingStatus.PENDING.value
    )
    db.add(entity)
    db.flush()

    # AML/OFAC sanctions screening on the entity name, run alongside KYC/KYB
    screening = screen_subject(db, "ENTITY", entity.id, entity.name)

    # Trigger KYC/KYB verification via Didit
    try:
        didit_client = get_didit_client()
        verification = didit_client.create_verification(
            entity_id=entity.id,
            entity_name=entity.name,
            entity_type="business",  # Default to business for B2B platform
            email=user_in.email
        )
        
        # Store verification ID on entity
        entity.verification_id = verification["verification_id"]
        entity.verification_url = verification.get("verification_url")
        
        # For demo/sandbox mode, auto-approve after verification creation
        # In production, this would wait for webhook callback. A sanctions
        # screening HIT always overrides auto-approval — an admin must clear it.
        if screening.status != "HIT" and os.getenv("AUTO_APPROVE_ONBOARDING", "False").lower() in ["true", "1"]:
            entity.onboarding_status = OnboardingStatus.APPROVED.value
        
        db.commit()
        
    except Exception as e:
        # Log error but don't fail registration - entity stays in PENDING
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create Didit verification: {e}")
        db.commit()

    # Create User
    user = User(
        name=user_in.name,
        email=user_in.email,
        entity_id=entity.id,
        password_hash=get_password_hash(user_in.password)
    )
    db.add(user)
    db.flush()

    # Assign Admin Role
    user_role = UserRole(
        user_id=user.id,
        role_id="ADMIN",
        entity_id=entity.id
    )
    db.add(user_role)
    db.commit()

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserMeOut)
def get_me(current_user: UserContext = Depends(get_current_user_context)):
    return {
        "id": current_user.user_id,
        "email": current_user.email,
        "name": current_user.name,
        "active_entity_id": current_user.active_entity_id,
        "roles": current_user.roles,
        "accessible_departments": current_user.accessible_departments
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

