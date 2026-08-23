import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON
from app.database import Base


class SanctionsScreening(Base):
    """Audit trail of every AML/OFAC watchlist screen run against an entity or vendor."""

    __tablename__ = "sanctions_screenings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject_type = Column(String(20), nullable=False)  # ENTITY, VENDOR
    subject_id = Column(String(36), nullable=False)
    subject_name = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # CLEAR, HIT, ERROR
    match_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
