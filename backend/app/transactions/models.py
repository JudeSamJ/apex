import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Integer
from sqlalchemy.orm import relationship
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    card_id = Column(String(36), ForeignKey("cards.id"), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    merchant_name = Column(String(255), nullable=False)
    merchant_mcc = Column(String(4), nullable=False)
    category = Column(String(100), nullable=True)  # Auto-coded category
    status = Column(String(20), nullable=False, default="HELD")  # HELD, SETTLED, DECLINED, REVERSED
    decline_reason = Column(String(255), nullable=True)
    gl_account_id = Column(String(36), ForeignKey("gl_accounts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    gl_account = relationship("GLAccount")

    entity = relationship("Entity")
    department = relationship("Department")
    card = relationship("Card")


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    source_event_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TransactionReceipt(Base):
    """A receipt (image/PDF) attached to a transaction for expense
    substantiation. Multiple receipts per transaction are allowed (e.g. a
    multi-page paper receipt photographed in parts)."""
    __tablename__ = "transaction_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=False)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    transaction = relationship("Transaction")
    uploaded_by = relationship("User")
