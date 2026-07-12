import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Integer, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Reimbursement(Base):
    __tablename__ = "reimbursements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)  # OUT_OF_POCKET, MILEAGE
    status = Column(String(30), nullable=False, default="SUBMITTED")  # SUBMITTED, APPROVED, REJECTED, REIMBURSED
    total_amount = Column(Numeric(18, 4), nullable=False)
    approval_id = Column(String(36), ForeignKey("approvals.id"), nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reimbursed_at = Column(DateTime, nullable=True)
    transfer_ref = Column(String(255), nullable=True)

    entity = relationship("Entity")
    department = relationship("Department")
    user = relationship("User")
    approval = relationship("Approval")
    line_items = relationship("ReimbursementLineItem", back_populates="reimbursement", cascade="all, delete-orphan")
    trips = relationship("MileageTrip", back_populates="reimbursement", cascade="all, delete-orphan")

class ReimbursementLineItem(Base):
    __tablename__ = "reimbursement_line_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    reimbursement_id = Column(String(36), ForeignKey("reimbursements.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    gl_account_id = Column(String(36), nullable=True)  # Set for Phase 3 sync
    custom_field_values = Column(JSON, nullable=True)
    receipt_url = Column(String(500), nullable=True)

    entity = relationship("Entity")
    reimbursement = relationship("Reimbursement", back_populates="line_items")

class MileageTrip(Base):
    __tablename__ = "mileage_trips"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    reimbursement_id = Column(String(36), ForeignKey("reimbursements.id", ondelete="CASCADE"), nullable=False)
    purpose = Column(String(500), nullable=False)
    mileage_rate = Column(Numeric(18, 4), nullable=False)
    total_miles = Column(Numeric(18, 4), nullable=False)
    computed_amount = Column(Numeric(18, 4), nullable=False)

    entity = relationship("Entity")
    reimbursement = relationship("Reimbursement", back_populates="trips")
    waypoints = relationship("TripWaypoint", back_populates="trip", cascade="all, delete-orphan")

class TripWaypoint(Base):
    __tablename__ = "trip_waypoints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    trip_id = Column(String(36), ForeignKey("mileage_trips.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    address = Column(String(500), nullable=False)
    lat = Column(Numeric(9, 6), nullable=True)
    lng = Column(Numeric(9, 6), nullable=True)

    entity = relationship("Entity")
    trip = relationship("MileageTrip", back_populates="waypoints")
