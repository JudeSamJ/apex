import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.disputes.models import CardDispute
from app.secrets.provider import get_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disputes", tags=["disputes"])

# A dispute in one of these states can still have evidence submitted against it.
OPEN_STATUSES = {"WARNING_NEEDS_RESPONSE", "UNDER_REVIEW"}


class DisputeOut(BaseModel):
    id: str
    card_id: Optional[str] = None
    transaction_id: Optional[str] = None
    stripe_dispute_id: str
    amount: float
    reason: Optional[str] = None
    status: str
    evidence_note: Optional[str] = None
    created_at: str
    updated_at: str


class EvidenceSubmit(BaseModel):
    evidence: str


def _to_out(d: CardDispute) -> dict:
    return {
        "id": d.id,
        "card_id": d.card_id,
        "transaction_id": d.transaction_id,
        "stripe_dispute_id": d.stripe_dispute_id,
        "amount": float(d.amount),
        "reason": d.reason,
        "status": d.status,
        "evidence_note": d.evidence_note,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


@router.get("", response_model=List[DisputeOut])
def list_disputes(
    status_filter: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    query = db.query(CardDispute).filter(CardDispute.entity_id == current_user.active_entity_id)
    if status_filter:
        query = query.filter(CardDispute.status == status_filter)
    rows = query.order_by(CardDispute.created_at.desc()).all()
    return [_to_out(r) for r in rows]


@router.post("/{dispute_id}/evidence", response_model=DisputeOut)
def submit_evidence(
    dispute_id: str,
    body: EvidenceSubmit,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Attach evidence to an open dispute and move it into review.

    When USE_REAL_ISSUING is on, this also submits the evidence to Stripe so
    the dispute actually progresses on their side; otherwise it's recorded
    locally only (sandbox/demo mode).
    """
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can respond to disputes")

    dispute = db.query(CardDispute).filter(
        CardDispute.id == dispute_id, CardDispute.entity_id == current_user.active_entity_id
    ).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status not in OPEN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Dispute is already {dispute.status} and cannot take new evidence")

    if os.getenv("USE_REAL_ISSUING", "False").lower() in ["true", "1"]:
        try:
            import stripe
            stripe.api_key = get_secret("STRIPE_SECRET_KEY")
            stripe.issuing.Dispute.modify(
                dispute.stripe_dispute_id,
                evidence={"reason": dispute.reason or "other", "explanation": body.evidence},
            )
        except Exception as e:
            logger.error(f"Failed to submit dispute evidence to Stripe for {dispute.stripe_dispute_id}: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to submit evidence to Stripe: {str(e)}")

    dispute.evidence_note = body.evidence
    dispute.status = "UNDER_REVIEW"
    db.commit()
    db.refresh(dispute)
    return _to_out(dispute)
