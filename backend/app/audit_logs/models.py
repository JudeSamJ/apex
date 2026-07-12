import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Who did it (null if system/webhook)
    action = Column(String(100), nullable=False)  # APPROVAL_DECISION, CARD_FREEZE, CARD_UNFREEZE, LIMIT_CHANGE, SYNC_RETRY, SWIPE_SIMULATION
    details = Column(JSON, nullable=True)  # Contextual parameters/logs
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    user = relationship("User")
