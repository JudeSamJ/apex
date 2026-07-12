from datetime import datetime, timedelta
from typing import Optional, List, Set
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app.entities_rbac.models import User, UserRole, Entity, OnboardingStatus

JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

class UserContext:
    def __init__(
        self,
        user_id: str,
        email: str,
        name: str,
        active_entity_id: str,
        active_entity_status: str,
        roles: List[str],
        accessible_departments: Optional[List[str]] = None,  # None means all
    ):
        self.user_id = user_id
        self.email = email
        self.name = name
        self.active_entity_id = active_entity_id
        self.active_entity_status = active_entity_status
        self.roles = roles
        self.accessible_departments = accessible_departments

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles

    @property
    def is_manager(self) -> bool:
        return "MANAGER" in self.roles

    @property
    def is_employee(self) -> bool:
        return "EMPLOYEE" in self.roles

    def check_active_entity_approved(self):
        if self.active_entity_status != OnboardingStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action blocked. Entity status is {self.active_entity_status} (must be APPROVED)."
            )

def get_current_user_context(
    token: Optional[str] = Depends(oauth2_scheme),
    x_entity_id: Optional[str] = Header(None, alias="X-Entity-Id"),
    db: Session = Depends(get_db)
) -> UserContext:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        # Fallback to standard admin user context for ease of testing or unauthenticated requests if header provided
        # Let's verify if we can extract user directly or if we require a token.
        # To make it robust and easy, let's look up by email or X-User-Id header if in mock environment.
        # This makes local testing/cURLing way easier.
        raise credentials_exception

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    # Determine active entity: default to user's primary entity, or switch to X-Entity-Id if user has a role there
    active_entity_id = x_entity_id or user.entity_id

    # Fetch user roles for this active entity
    user_roles = db.query(UserRole).filter(
        UserRole.user_id == user.id,
        UserRole.entity_id == active_entity_id
    ).all()

    # If user has no roles in the requested entity, block
    if not user_roles:
        # Check if the active_entity_id is a child entity of the user's primary entity (to support parent/child)
        entity = db.query(Entity).filter(Entity.id == active_entity_id).first()
        if entity and entity.parent_entity_id == user.entity_id:
            # For parent company users, let's inherit roles from parent entity
            user_roles = db.query(UserRole).filter(
                UserRole.user_id == user.id,
                UserRole.entity_id == user.entity_id
            ).all()
        
        if not user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to entity {active_entity_id}"
            )

    active_entity = db.query(Entity).filter(Entity.id == active_entity_id).first()
    if not active_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )

    roles = [ur.role_id for ur in user_roles]
    
    # Determine accessible departments
    # If the user has an ADMIN role or is a BOOKKEEPER, they have full access to all departments
    if "ADMIN" in roles or "BOOKKEEPER" in roles:
        accessible_departments = None
    else:
        # Otherwise, compile list of department_ids they have roles in
        accessible_departments = [ur.department_id for ur in user_roles if ur.department_id is not None]

    return UserContext(
        user_id=user.id,
        email=user.email,
        name=user.name,
        active_entity_id=active_entity_id,
        active_entity_status=active_entity.onboarding_status,
        roles=roles,
        accessible_departments=accessible_departments
    )
