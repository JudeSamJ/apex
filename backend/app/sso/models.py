import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SSOConnection(Base):
    """An entity's enterprise SSO configuration — one per entity, keyed by the
    email domain whose users should authenticate via the IdP instead of a
    password. Real setup requires the customer's IT admin to configure their
    IdP via the WorkOS Admin Portal (admin_portal_url) before it goes ACTIVE;
    the mock client activates immediately for sandbox/demo use."""

    __tablename__ = "sso_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False, unique=True)
    domain = Column(String(255), nullable=False, unique=True)
    provider = Column(String(50), nullable=False, default="WORKOS")
    workos_organization_id = Column(String(255), nullable=True)
    workos_connection_id = Column(String(255), nullable=True)
    admin_portal_url = Column(String(1000), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, ACTIVE
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
