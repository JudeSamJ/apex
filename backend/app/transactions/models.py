import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime
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
