import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class GLAccount(Base):
    __tablename__ = "gl_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # ASSET, LIABILITY, EXPENSE, REVENUE
    is_active = Column(Boolean, nullable=False, default=True)
    external_id = Column(String(255), nullable=True)  # External ERP system ID (e.g., QBO account ID)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")

class GLMapping(Base):
    __tablename__ = "gl_mappings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    mapping_type = Column(String(50), nullable=False)  # MCC, VENDOR, DEPARTMENT
    source_value = Column(String(255), nullable=False)  # e.g., "4816" (MCC) or vendor_id or dept_id
    gl_account_id = Column(String(36), ForeignKey("gl_accounts.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    gl_account = relationship("GLAccount")

class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    record_type = Column(String(50), nullable=False)  # TRANSACTION, BILL, REIMBURSEMENT
    record_id = Column(String(36), nullable=False)
    gl_account_id = Column(String(36), ForeignKey("gl_accounts.id"), nullable=False)
    status = Column(String(30), nullable=False, default="SYNC_READY")  # SYNC_READY, SYNCING, SYNCED, ERROR
    error_message = Column(String(500), nullable=True)
    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    gl_account = relationship("GLAccount")

class AccountingCustomField(Base):
    __tablename__ = "accounting_custom_fields"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    field_type = Column(String(20), nullable=False)  # TEXT, SELECT
    select_options = Column(JSON, nullable=True)  # List of strings for SELECT field
    is_required = Column(Boolean, nullable=False, default=False)

    entity = relationship("Entity")


class ERPConnection(Base):
    __tablename__ = "erp_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    provider = Column(String(50), nullable=False)  # QBO, NETSUITE, XERO
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=True)
    realm_id = Column(String(255), nullable=True)  # QBO specific
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
