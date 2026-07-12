import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Integer, DateTime, Numeric, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class ApprovalState(str):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    approvable_type = Column(String(50), nullable=False)  # CARD_REQUEST, BILL, REIMBURSEMENT
    approvable_id = Column(String(36), nullable=False)
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    current_step = Column(Integer, nullable=False, default=1)
    total_steps = Column(Integer, nullable=False, default=0)
    state = Column(String(30), nullable=False, default="SUBMITTED")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    department = relationship("Department")
    steps = relationship("ApprovalStep", back_populates="approval", cascade="all, delete-orphan")

class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    approval_id = Column(String(36), ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    approver_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Null if role-based
    approver_role = Column(String(50), nullable=True)  # ADMIN, MANAGER, AP_APPROVER
    decision = Column(String(20), nullable=False, default="PENDING")  # PENDING, APPROVED, REJECTED
    decided_at = Column(DateTime, nullable=True)
    comment = Column(String(500), nullable=True)

    approval = relationship("Approval", back_populates="steps")
    approver = relationship("User")
    entity = relationship("Entity")

class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    applies_to = Column(String(50), nullable=False)  # CARD_REQUEST, BILL, REIMBURSEMENT
    min_amount = Column(Numeric(18, 4), nullable=False, default=0)
    max_amount = Column(Numeric(18, 4), nullable=True)
    required_steps = Column(JSON, nullable=False)  # List of roles: e.g. ["MANAGER", "ADMIN"]

    entity = relationship("Entity")
