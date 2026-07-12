import uuid
from datetime import datetime
from sqlalchemy import Column, String, Numeric, DateTime, UniqueConstraint
from app.database import Base
from enum import Enum

class EntryType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

class LedgerState(str, Enum):
    PENDING_AUTH = "PENDING_AUTH"
    HELD = "HELD"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    REVERSED = "REVERSED"

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", "entry_type", name="uq_idempotency_entry_type"),
        {"schema": "ledger"}
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), nullable=False)
    department_id = Column(String(36), nullable=False)
    card_id = Column(String(36), nullable=True)  # Nullable for non-card postings
    transaction_id = Column(String(36), nullable=False)
    entry_type = Column(String(10), nullable=False)  # DEBIT or CREDIT
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    state = Column(String(20), nullable=False, default=LedgerState.PENDING_AUTH.value)
    source_event_id = Column(String(36), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
