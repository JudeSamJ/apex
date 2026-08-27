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
    create_password_reset_token,
    decode_password_reset_token,
    get_current_user_context,
    UserContext
)
from app.notifications.client import get_email_client

logger = logging.getLogger(__name__)

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

class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

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
    from app.rate_limit import check_rate_limit
    # Keyed by the submitted username so a stolen/guessed email can't be
    # brute-forced against unlimited passwords — checked before the DB
    # lookup so it applies the same whether or not the account exists.
    check_rate_limit(user_id=form_data.username, endpoint="login", limit=10, window_seconds=300)

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

@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Always returns the same generic message whether or not the email is
    registered — enumerating valid accounts to an anonymous caller is its
    own vulnerability. If the account exists, a reset link is emailed."""
    from app.rate_limit import check_rate_limit
    check_rate_limit(user_id=body.email, endpoint="forgot_password", limit=5, window_seconds=900)

    generic_response = {"message": "If an account exists for that email, a password reset link has been sent."}

    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        return generic_response

    reset_token = create_password_reset_token(user.id, user.password_hash)
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
    reset_link = f"{frontend_base}/?reset_token={reset_token}"

    try:
        get_email_client().send(
            to=user.email,
            subject="Reset your Apex password",
            body=f"Someone requested a password reset for your Apex account. This link expires in 30 minutes:\n\n{reset_link}\n\nIf you didn't request this, you can ignore this email."
        )
    except Exception as e:
        logger.warning(f"Failed to send password reset email to {user.email}: {e}")

    return generic_response

@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    from app.rate_limit import check_rate_limit
    check_rate_limit(user_id=body.token[:32], endpoint="reset_password", limit=10, window_seconds=900)

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # The token embeds a fingerprint of the password hash at issuance time —
    # decode against every user isn't possible without knowing who first, so
    # peek at the unverified payload's `sub` just to load the row, then let
    # decode_password_reset_token do the real signature+fingerprint check.
    from jose import jwt as _jwt
    try:
        unverified = _jwt.get_unverified_claims(body.token)
    except Exception:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    user = db.query(User).filter(User.id == unverified.get("sub")).first()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    decode_password_reset_token(body.token, user.password_hash)

    user.password_hash = get_password_hash(body.new_password)
    db.commit()
    return {"message": "Password reset. You can now sign in with your new password."}

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
    base_currency: str = "USD"

class DepartmentOut(BaseModel):
    id: str
    entity_id: str
    name: str

DEFAULT_DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance"]


def is_root_entity_admin(current_user: UserContext, db: Session) -> bool:
    """Whether this user administers a top-level company.

    A root entity is one with no parent (Apex Corporation in the seeded demo
    data); its admins are the only people who can approve a company someone
    else created. An admin of a subsidiary administers that subsidiary only.
    """
    if not current_user.is_admin:
        return False
    entity = db.query(Entity).filter(Entity.id == current_user.active_entity_id).first()
    return bool(entity and entity.parent_entity_id is None)


def require_root_entity_admin(current_user: UserContext, db: Session) -> None:
    if not is_root_entity_admin(current_user, db):
        raise HTTPException(
            status_code=403,
            detail="Only an admin of a top-level company can review company onboarding",
        )


class EntityCreate(BaseModel):
    name: str
    base_currency: Optional[str] = None
    # Omitted, the company stands on its own. Set it to nest the new company
    # under an existing one as a subsidiary.
    parent_entity_id: Optional[str] = None
    # Omitted, DEFAULT_DEPARTMENTS are created. A company with no department
    # at all cannot issue cards — card requests resolve a department and 400
    # with "No department set up for this entity".
    departments: Optional[List[str]] = None


@router.post("/entities", response_model=EntityOut)
def create_entity(
    entity_in: EntityCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Create a company.

    Created live by a root-entity admin, and PENDING for anyone else — the
    same shape as card requests, where a request from someone who already
    outranks every approver has nobody left to wait on. A PENDING company
    exists but is barred from transacting until a root-entity admin approves
    it (check_active_entity_approved gates every money-moving endpoint).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can create companies")

    name = entity_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")

    if db.query(Entity).filter(Entity.name == name).first():
        raise HTTPException(status_code=400, detail=f"A company named '{name}' already exists")

    from app.fx.client import SUPPORTED_CURRENCIES
    base_currency = (entity_in.base_currency or "USD").upper()
    if base_currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported base currency; must be one of {sorted(SUPPORTED_CURRENCIES)}",
        )

    parent_entity_id = entity_in.parent_entity_id
    if parent_entity_id:
        parent = db.query(Entity).filter(Entity.id == parent_entity_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent company not found")

    created_live = is_root_entity_admin(current_user, db)
    entity = Entity(
        name=name,
        onboarding_status=(
            OnboardingStatus.APPROVED.value if created_live else OnboardingStatus.PENDING.value
        ),
        parent_entity_id=parent_entity_id,
        base_currency=base_currency,
    )
    db.add(entity)
    db.flush()

    for dept_name in (entity_in.departments or DEFAULT_DEPARTMENTS):
        dept_name = dept_name.strip()
        if dept_name:
            db.add(Department(entity_id=entity.id, name=dept_name))

    # The creator needs a role on the new company or they cannot switch into
    # the thing they just made — get_current_user_context rejects an entity the
    # user holds no role in, and only inherits roles down to a subsidiary of
    # the user's own primary entity.
    db.add(UserRole(user_id=current_user.user_id, role_id="ADMIN", entity_id=entity.id))

    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=entity.id,
        user_id=current_user.user_id,
        action="ENTITY_CREATED",
        details={
            "name": entity.name,
            "base_currency": entity.base_currency,
            "parent_entity_id": entity.parent_entity_id,
            "onboarding_status": entity.onboarding_status,
            "created_by": current_user.email,
        },
    )
    db.commit()
    db.refresh(entity)

    if not created_live:
        # Tell the people who can actually approve it. Root-entity admins hold
        # their ADMIN role on the root entity, not on this pending one.
        from app.notifications.service import notify_users_with_role
        for root in db.query(Entity).filter(Entity.parent_entity_id.is_(None)).all():
            notify_users_with_role(
                db=db,
                entity_id=root.id,
                role_id="ADMIN",
                type="APPROVAL_REQUESTED",
                title="New company awaiting approval",
                body=f"{current_user.name} created '{entity.name}', which needs onboarding approval.",
            )
        db.commit()

    return entity


@router.get("/entities", response_model=List[EntityOut])
def list_entities(db: Session = Depends(get_db)):
    return db.query(Entity).all()


@router.get("/entities/pending", response_model=List[EntityOut])
def list_pending_entities(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Companies awaiting onboarding approval, for the root admin's queue."""
    require_root_entity_admin(current_user, db)
    return db.query(Entity).filter(
        Entity.onboarding_status == OnboardingStatus.PENDING.value
    ).all()

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
    # Any admin used to be able to flip any company's onboarding status,
    # including their own from PENDING to APPROVED — self-approval. Approving a
    # company is a root-entity admin's call.
    require_root_entity_admin(current_user, db)

    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if status not in [OnboardingStatus.APPROVED.value, OnboardingStatus.PENDING.value, OnboardingStatus.SUSPENDED.value]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    previous_status = entity.onboarding_status
    entity.onboarding_status = status

    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=entity.id,
        user_id=current_user.user_id,
        action="ENTITY_STATUS_CHANGED",
        details={
            "name": entity.name,
            "from": previous_status,
            "to": status,
            "changed_by": current_user.email,
        },
    )
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

