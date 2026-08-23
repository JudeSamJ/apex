import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class SpendProgram(Base):
    __tablename__ = "spend_programs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    limit_amount = Column(Numeric(18, 4), nullable=False)
    limit_type = Column(String(50), nullable=False)  # MONTHLY, YEARLY, ONETIME
    allowed_mcc = Column(JSON, nullable=True)  # List of allowed MCC codes, e.g. ["5812", "5411"] or null for all
    approval_threshold = Column(Numeric(18, 4), nullable=True)  # Txns above this amount require approval

    entity = relationship("Entity")

class Card(Base):
    __tablename__ = "cards"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    spend_program_id = Column(String(36), ForeignKey("spend_programs.id"), nullable=False)
    type = Column(String(20), nullable=False)  # VIRTUAL, PHYSICAL
    limit_amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")  # currency the card actually spends in
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, FROZEN
    masked_pan = Column(String(30), nullable=False)  # e.g., **** **** **** 4242
    card_token = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    owner = relationship("User")
    department = relationship("Department")
    spend_program = relationship("SpendProgram")

class CardRequest(Base):
    __tablename__ = "card_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    spend_program_id = Column(String(36), ForeignKey("spend_programs.id"), nullable=False)
    type = Column(String(20), nullable=False)  # VIRTUAL, PHYSICAL
    limit_amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")  # currency the card will spend in
    status = Column(String(20), nullable=False, default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, REJECTED
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    requester = relationship("User")
    department = relationship("Department")
    spend_program = relationship("SpendProgram")
