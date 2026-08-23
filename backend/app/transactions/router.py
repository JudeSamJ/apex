import csv
import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
import uuid

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.cards.models import Card
from app.transactions.models import Transaction
from app.ledger.client import LedgerClient
from app.transactions.tasks import process_settlement
from app.transactions.pipeline_events import emit_pipeline_event

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

class SwipeSimulation(BaseModel):
    card_id: str
    amount: Decimal
    merchant_name: str
    merchant_mcc: str

class TransactionOut(BaseModel):
    id: str
    owner_name: str
    masked_pan: str
    amount: Decimal
    currency: str
    merchant_name: str
    merchant_mcc: str
    category: Optional[str] = None
    status: str
    decline_reason: Optional[str] = None
    created_at: str

@router.get("", response_model=List[TransactionOut])
def list_transactions(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(Transaction).join(Card, Transaction.card_id == Card.id).filter(
        Transaction.entity_id == current_user.active_entity_id
    )

    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        query = query.filter(Card.owner_id == current_user.user_id)

    txs = query.order_by(Transaction.created_at.desc()).all()
    out = []
    for tx in txs:
        out.append({
            "id": tx.id,
            "owner_name": tx.card.owner.name,
            "masked_pan": tx.card.masked_pan,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant_name,
            "merchant_mcc": tx.merchant_mcc,
            "category": tx.category,
            "status": tx.status,
            "decline_reason": tx.decline_reason,
            "created_at": tx.created_at.isoformat()
        })
    return out

@router.get("/export.csv")
def export_transactions_csv(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """CSV statement export — same visibility rules as the list endpoint
    (non-admin/bookkeeper users only see their own card's transactions)."""
    query = db.query(Transaction).join(Card, Transaction.card_id == Card.id).filter(
        Transaction.entity_id == current_user.active_entity_id
    )

    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        query = query.filter(Card.owner_id == current_user.user_id)

    txs = query.order_by(Transaction.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "date", "owner", "card", "merchant", "mcc", "category",
        "amount", "currency", "status", "decline_reason"
    ])
    for tx in txs:
        writer.writerow([
            tx.id,
            tx.created_at.isoformat(),
            tx.card.owner.name,
            tx.card.masked_pan,
            tx.merchant_name,
            tx.merchant_mcc,
            tx.category or "",
            tx.amount,
            tx.currency,
            tx.status,
            tx.decline_reason or "",
        ])
    buffer.seek(0)

    filename = f"transactions_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.post("/simulate-swipe")
def simulate_swipe(
    swipe: SwipeSimulation,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    
    # 1. Fetch card with row-level locking
    card = db.query(Card).filter(
        Card.id == swipe.card_id,
        Card.entity_id == current_user.active_entity_id
    ).with_for_update().first()

    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Helper function to record decline
    def decline(reason: str):
        declined_tx = Transaction(
            id=str(uuid.uuid4()),
            entity_id=card.entity_id,
            department_id=card.department_id,
            card_id=card.id,
            amount=swipe.amount,
            currency="USD",
            merchant_name=swipe.merchant_name,
            merchant_mcc=swipe.merchant_mcc,
            status="DECLINED",
            decline_reason=reason
        )
        db.add(declined_tx)
        db.commit()
        return {
            "status": "DECLINED",
            "decline_reason": reason,
            "transaction_id": declined_tx.id
        }

    # 2. Check Card Status
    if card.status == "FROZEN":
        return decline("Card is frozen")

    # 3. Check Spend Program limits (policy-driven, not hardcoded card-only)
    program = card.spend_program
    program_cycle_spend = db.query(func.sum(Transaction.amount)).join(
        Card, Transaction.card_id == Card.id
    ).filter(
        Card.spend_program_id == program.id,
        Transaction.status.in_(["HELD", "SETTLED"])
    ).scalar() or Decimal("0.0000")

    if program_cycle_spend + swipe.amount > program.limit_amount:
        return decline("Exceeds spend program limit")

    # 4. Check card-level limit (card limit must be <= program limit)
    current_cycle_spend = db.query(func.sum(Transaction.amount)).filter(
        Transaction.card_id == card.id,
        Transaction.status.in_(["HELD", "SETTLED"])
    ).scalar() or Decimal("0.0000")

    if current_cycle_spend + swipe.amount > card.limit_amount:
        return decline("Exceeds card limit")

    # 5. Check allowed MCC categories on spend program
    if program.allowed_mcc and swipe.merchant_mcc not in program.allowed_mcc:
        return decline("Merchant category not allowed by spend program")

    # 6. Success Path - Authorize (HELD)
    transaction_id = str(uuid.uuid4())
    idempotency_key = f"hold_{transaction_id}"
    
    # Write to Ledger Core first
    try:
        LedgerClient.post_hold(
            db=db,
            entity_id=card.entity_id,
            department_id=card.department_id,
            card_id=card.id,
            transaction_id=transaction_id,
            amount=swipe.amount,
            currency="USD",
            idempotency_key=idempotency_key,
            source_event_id=transaction_id
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ledger authorization failed: {str(e)}")

    # Create Transaction record
    tx = Transaction(
        id=transaction_id,
        entity_id=card.entity_id,
        department_id=card.department_id,
        card_id=card.id,
        amount=swipe.amount,
        currency="USD",
        merchant_name=swipe.merchant_name,
        merchant_mcc=swipe.merchant_mcc,
        status="HELD"
    )
    db.add(tx)
    emit_pipeline_event(db, card.entity_id, transaction_id, "hold_created", transaction_id)
    db.commit()

    # Trigger async settlement task via Celery
    process_settlement.delay(tx.id, float(tx.amount))

    return {
        "status": "APPROVED (HELD)",
        "transaction_id": tx.id,
        "amount": tx.amount,
        "merchant_name": tx.merchant_name
    }
