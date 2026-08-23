import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON, UniqueConstraint
from app.database import Base


class IdempotencyKey(Base):
    """Guards money-movement endpoints against duplicate execution on retry.

    A row is inserted (empty response) before the protected action runs, using
    the DB unique constraint as the atomic lock. If a concurrent or retried
    request hits the same key while the row has no response yet, it means the
    original request is still in flight; once the row is filled in, later
    retries replay the stored response instead of re-executing the action.
    """

    __tablename__ = "idempotency_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String(255), nullable=False)
    endpoint = Column(String(100), nullable=False)
    entity_id = Column(String(36), nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("key", "endpoint", "entity_id", name="uq_idempotency_key_endpoint_entity"),
    )
