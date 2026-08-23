import csv
import io
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Response
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
from app.transactions.models import Transaction, TransactionReceipt
from app.ledger.client import LedgerClient
from app.transactions.tasks import process_settlement
from app.transactions.pipeline_events import emit_pipeline_event
from app.transactions.storage import save_receipt, read_receipt, delete_receipt, ALLOWED_CONTENT_TYPES, MAX_RECEIPT_BYTES
from app.money import MoneyOut

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
    amount: MoneyOut
    currency: str
    merchant_name: str
    merchant_mcc: str
    category: Optional[str] = None
    status: str
    decline_reason: Optional[str] = None
    created_at: str

@router.get("", response_model=List[TransactionOut])
def list_transactions(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(Transaction).join(Card, Transaction.card_id == Card.id).filter(
        Transaction.entity_id == current_user.active_entity_id
    )

    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        query = query.filter(Card.owner_id == current_user.user_id)

    # Unbounded before this — every card swipe adds a row here, and the
    # frontend polls this endpoint every 5 seconds, so an account with a
    # real transaction history would make every poll progressively slower.
    response.headers["X-Total-Count"] = str(query.count())
    txs = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()
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

    # A card always spends in its own currency — real cards settle in their
    # billing currency regardless of the merchant's local currency, so the
    # card itself (not the caller) is the source of truth here.
    swipe_currency = card.currency

    # Helper function to record decline
    def decline(reason: str):
        declined_tx = Transaction(
            id=str(uuid.uuid4()),
            entity_id=card.entity_id,
            department_id=card.department_id,
            card_id=card.id,
            amount=swipe.amount,
            currency=swipe_currency,
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

    # Card/program limit_amount is denominated in the entity's base
    # currency (the policy currency finance sets limits in), which may
    # differ from what this card actually spends in — so both prior spend
    # and this swipe must be converted before comparing against a limit.
    from app.entities_rbac.models import Entity
    from app.fx.service import convert, sum_converted

    base_currency = db.query(Entity.base_currency).filter(Entity.id == card.entity_id).scalar() or "USD"
    swipe_amount_in_base = convert(swipe.amount, swipe_currency, base_currency)

    # 3. Check Spend Program limits (policy-driven, not hardcoded card-only)
    program = card.spend_program
    program_cycle_rows = db.query(Transaction.amount, Transaction.currency).join(
        Card, Transaction.card_id == Card.id
    ).filter(
        Card.spend_program_id == program.id,
        Transaction.status.in_(["HELD", "SETTLED"])
    ).all()
    program_cycle_spend = sum_converted(program_cycle_rows, base_currency)

    if program_cycle_spend + swipe_amount_in_base > program.limit_amount:
        return decline("Exceeds spend program limit")

    # 4. Check card-level limit (card limit must be <= program limit)
    current_cycle_rows = db.query(Transaction.amount, Transaction.currency).filter(
        Transaction.card_id == card.id,
        Transaction.status.in_(["HELD", "SETTLED"])
    ).all()
    current_cycle_spend = sum_converted(current_cycle_rows, base_currency)

    if current_cycle_spend + swipe_amount_in_base > card.limit_amount:
        return decline("Exceeds card limit")

    # 5. Check allowed MCC categories on spend program
    if program.allowed_mcc and swipe.merchant_mcc not in program.allowed_mcc:
        return decline("Merchant category not allowed by spend program")

    # 5b. Per-card velocity controls (admin-configurable, independent of the
    # cumulative program/card limit checks above).
    if card.single_txn_limit is not None and swipe.amount > card.single_txn_limit:
        return decline("Exceeds this card's single-transaction limit")

    if card.daily_txn_count_limit is not None:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        todays_count = db.query(Transaction).filter(
            Transaction.card_id == card.id,
            Transaction.status.in_(["HELD", "SETTLED"]),
            Transaction.created_at >= today_start
        ).count()
        if todays_count >= card.daily_txn_count_limit:
            return decline("Card has reached its daily transaction limit")

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
            currency=swipe_currency,
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
        currency=swipe_currency,
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


class ReceiptOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str
    created_at: str


def _get_transaction_for_receipt_access(
    transaction_id: str, current_user: UserContext, db: Session
) -> Transaction:
    """A transaction's receipts are visible/manageable by the same people
    who can see the transaction itself: the card's owner, or an
    admin/bookkeeper on the entity."""
    tx = db.query(Transaction).join(Card, Transaction.card_id == Card.id).filter(
        Transaction.id == transaction_id,
        Transaction.entity_id == current_user.active_entity_id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        if tx.card.owner_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="You don't have access to this transaction")

    return tx


@router.post("/{transaction_id}/receipts", response_model=ReceiptOut)
def upload_receipt(
    transaction_id: str,
    file: UploadFile = File(...),
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    tx = _get_transaction_for_receipt_access(transaction_id, current_user, db)

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Allowed: images or PDF.")

    data = file.file.read()
    if len(data) > MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    storage_path = save_receipt(transaction_id, file.filename, data)

    receipt = TransactionReceipt(
        entity_id=tx.entity_id,
        transaction_id=transaction_id,
        uploaded_by_user_id=current_user.user_id,
        filename=file.filename or "receipt",
        content_type=file.content_type,
        size_bytes=len(data),
        storage_path=storage_path
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return {
        "id": receipt.id,
        "filename": receipt.filename,
        "content_type": receipt.content_type,
        "size_bytes": receipt.size_bytes,
        "uploaded_by_name": current_user.name,
        "created_at": receipt.created_at.isoformat()
    }


@router.get("/{transaction_id}/receipts", response_model=List[ReceiptOut])
def list_receipts(
    transaction_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    _get_transaction_for_receipt_access(transaction_id, current_user, db)

    receipts = db.query(TransactionReceipt).filter(
        TransactionReceipt.transaction_id == transaction_id
    ).order_by(TransactionReceipt.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "content_type": r.content_type,
            "size_bytes": r.size_bytes,
            "uploaded_by_name": r.uploaded_by.name,
            "created_at": r.created_at.isoformat()
        }
        for r in receipts
    ]


@router.get("/receipts/{receipt_id}/file")
def download_receipt(
    receipt_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    receipt = db.query(TransactionReceipt).filter(
        TransactionReceipt.id == receipt_id,
        TransactionReceipt.entity_id == current_user.active_entity_id
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    _get_transaction_for_receipt_access(receipt.transaction_id, current_user, db)

    try:
        data = read_receipt(receipt.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Receipt file is missing from storage")

    return StreamingResponse(
        io.BytesIO(data),
        media_type=receipt.content_type,
        headers={"Content-Disposition": f'inline; filename="{receipt.filename}"'}
    )


@router.delete("/receipts/{receipt_id}")
def delete_receipt_endpoint(
    receipt_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    receipt = db.query(TransactionReceipt).filter(
        TransactionReceipt.id == receipt_id,
        TransactionReceipt.entity_id == current_user.active_entity_id
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    _get_transaction_for_receipt_access(receipt.transaction_id, current_user, db)

    if receipt.uploaded_by_user_id != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only the uploader or an admin can delete this receipt")

    delete_receipt(receipt.storage_path)
    db.delete(receipt)
    db.commit()
    return {"message": "Receipt deleted"}
