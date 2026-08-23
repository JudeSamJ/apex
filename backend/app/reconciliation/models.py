import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ReconciliationRun(Base):
    """One reconciliation pass comparing local ledger/payment state against
    the payment rail provider, to catch drift between our records and theirs."""

    __tablename__ = "reconciliation_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    provider = Column(String(50), nullable=False)  # PAYMENT_RAIL
    status = Column(String(20), nullable=False, default="RUNNING")  # RUNNING, COMPLETED, FAILED
    checked_count = Column(Integer, nullable=False, default=0)
    discrepancy_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    entity = relationship("Entity")


class ReconciliationDiscrepancy(Base):
    """A single record where our local status disagreed with the provider's."""

    __tablename__ = "reconciliation_discrepancies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False)
    subject_type = Column(String(20), nullable=False)  # BILL_PAYMENT, REIMBURSEMENT
    subject_id = Column(String(36), nullable=False)
    transfer_ref = Column(String(255), nullable=False)
    local_status = Column(String(30), nullable=False)
    provider_status = Column(String(30), nullable=False)
    amount = Column(Numeric(18, 4), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved = Column(String(20), nullable=True)  # None (open), RETRIED, ACKNOWLEDGED
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    run = relationship("ReconciliationRun")
