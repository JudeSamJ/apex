import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class MerchantNormalization(Base):
    __tablename__ = "merchant_normalizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    raw_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)

    entity = relationship("Entity")

class Insight(Base):
    __tablename__ = "insights"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    type = Column(String(50), nullable=False)  # DUPLICATE_SUBSCRIPTION, PRICE_INCREASE
    status = Column(String(30), nullable=False, default="OPEN")  # OPEN, CONFIRMED, DISMISSED
    severity = Column(String(20), nullable=False, default="LOW")  # LOW, MEDIUM, HIGH
    description = Column(String(500), nullable=False)
    potential_savings = Column(Numeric(18, 4), nullable=False, default=0.0)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
