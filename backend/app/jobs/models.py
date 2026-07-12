import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime, Integer, Text
from sqlalchemy.orm import relationship
from app.database import Base

class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    job_type = Column(String(50), nullable=False)  # SETTLEMENT, INSIGHT_DETECTION, ERP_SYNC, PAYMENT_RAIL
    source_event_id = Column(String(36), nullable=False)  # Reference ID (e.g. transaction_id, bill_id)
    status = Column(String(30), nullable=False, default="PENDING")  # PENDING, COMPLETED, FAILED
    retries = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    entity = relationship("Entity")
