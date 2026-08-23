import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    default_gl_account_id = Column(String(36), nullable=True)  # Placeholder for Phase 3 sync
    screening_status = Column(String(20), nullable=False, default="CLEAR")  # CLEAR, HIT, ERROR

    entity = relationship("Entity")

class VendorContact(Base):
    __tablename__ = "vendor_contacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    vendor_id = Column(String(36), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)

    entity = relationship("Entity")
    vendor = relationship("Vendor")

class VendorBankAccount(Base):
    __tablename__ = "vendor_bank_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    vendor_id = Column(String(36), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    masked_account_ref = Column(String(255), nullable=False)  # token representing banking detail
    # Plaid-specific fields for real bank account linking
    plaid_access_token = Column(String(255), nullable=True)
    plaid_item_id = Column(String(255), nullable=True)
    plaid_account_id = Column(String(255), nullable=True)

    entity = relationship("Entity")
    vendor = relationship("Vendor")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)  # Attributed dept
    vendor_id = Column(String(36), ForeignKey("vendors.id"), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT")  # DRAFT, PENDING_APPROVAL, APPROVED, PAID, VOID
    due_date = Column(DateTime, nullable=False)
    total_amount = Column(Numeric(18, 4), nullable=False)
    payment_method = Column(String(20), nullable=False)  # CARD, BANK_TRANSFER
    approval_id = Column(String(36), ForeignKey("approvals.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    department = relationship("Department")
    vendor = relationship("Vendor")
    approval = relationship("Approval")
    line_items = relationship("BillLineItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("BillPayment", back_populates="bill", cascade="all, delete-orphan")

class BillLineItem(Base):
    __tablename__ = "bill_line_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    bill_id = Column(String(36), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    gl_account_id = Column(String(36), nullable=True)  # Set for Phase 3 sync
    custom_field_values = Column(JSON, nullable=True)

    entity = relationship("Entity")
    bill = relationship("Bill", back_populates="line_items")

class BillPayment(Base):
    __tablename__ = "bill_payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    bill_id = Column(String(36), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(String(36), nullable=True)  # References public.transactions.id
    transfer_ref = Column(String(255), nullable=True)   # References mock payment rail transfer_ref
    paid_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entity = relationship("Entity")
    bill = relationship("Bill", back_populates="payments")
