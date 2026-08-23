import uuid
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base


class CardDispute(Base):
    """A cardholder dispute/chargeback raised on a settled card transaction,
    mirrored locally from Stripe Issuing's issuing_dispute.* webhook events."""

    __tablename__ = "card_disputes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    card_id = Column(String(36), ForeignKey("cards.id"), nullable=True)
    transaction_id = Column(String(36), nullable=True)  # references ledger.transactions, cross-schema
    stripe_dispute_id = Column(String(255), nullable=False, unique=True)
    amount = Column(Numeric(18, 4), nullable=False)
    reason = Column(String(100), nullable=True)
    # WARNING_NEEDS_RESPONSE, UNDER_REVIEW, WON, LOST, EXPIRED, ACCEPTED
    status = Column(String(30), nullable=False, default="WARNING_NEEDS_RESPONSE")
    evidence_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    entity = relationship("Entity")
    card = relationship("Card")
