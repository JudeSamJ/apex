import uuid
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from enum import Enum

class OnboardingStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"

class Entity(Base):
    __tablename__ = "entities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    onboarding_status = Column(String(50), nullable=False, default=OnboardingStatus.PENDING.value)
    parent_entity_id = Column(String(36), ForeignKey("entities.id"), nullable=True)

    parent = relationship("Entity", remote_side=[id], backref="subsidiaries")

class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    name = Column(String(255), nullable=False)

    entity = relationship("Entity")

class Location(Base):
    __tablename__ = "locations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=False)

    entity = relationship("Entity")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)  # For auth

    entity = relationship("Entity")
    roles = relationship("UserRole", back_populates="user")

class Role(Base):
    __tablename__ = "roles"

    id = Column(String(50), primary_key=True)  # ADMIN, MANAGER, EMPLOYEE, AP_APPROVER, BOOKKEEPER
    name = Column(String(255), nullable=False)

class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "entity_id", "department_id", name="uq_user_role_dept"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String(50), ForeignKey("roles.id"), nullable=False)
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)

    user = relationship("User", back_populates="roles")
    role = relationship("Role")
    entity = relationship("Entity")
    department = relationship("Department")
