import os
import logging
import hmac
import hashlib
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.database import get_db
from app.ledger.client import LedgerClient
from app.transactions.pipeline_events import emit_pipeline_event
from app.kyc.client import get_didit_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DWOLLA_WEBHOOK_SECRET = os.getenv("DWOLLA_WEBHOOK_SECRET", "")
DIDIT_WEBHOOK_SECRET = os.getenv("DIDIT_WEBHOOK_SECRET", "")


def _verify_hmac_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 signature check shared by the Dwolla/Didit handlers."""
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _require_valid_signature(
    provider: str, payload: bytes, signature: str, secret: str
) -> None:
    """Reject the webhook unless it carries a valid signature for the configured secret.

    When no secret is configured (sandbox/demo mode, no dashboard access to set one
    up yet) verification is skipped but loudly logged, matching the existing Stripe
    handler's behavior — this must not be the default in production.
    """
    if not secret:
        logger.warning(
            f"{provider}_WEBHOOK_SECRET not set; skipping {provider} webhook signature "
            "verification (sandbox mode only — set the secret before going live)"
        )
        return
    if not _verify_hmac_signature(payload, signature, secret):
        logger.error(f"Invalid {provider} webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")


@router.post("/dwolla")
async def dwolla_webhook(
    request: Request,
    x_request_signature_sha256: str = Header(None, alias="X-Request-Signature-SHA256"),
    db: Session = Depends(get_db)
):
    """Handle Dwolla webhook events for transfer status updates."""

    payload = await request.body()

    # Dwolla signs webhooks with HMAC-SHA256 of the raw body in
    # X-Request-Signature-SHA256, keyed by the app secret configured in the
    # Dwolla dashboard (DWOLLA_WEBHOOK_SECRET here).
    _require_valid_signature("Dwolla", payload, x_request_signature_sha256, DWOLLA_WEBHOOK_SECRET)

    import json
    event = json.loads(payload)

    event_topic = event.get("topic")
    event_id = event.get("id")
    event_data = event.get("_links", {}).get("resource", {}).get("href", "")
    
    logger.info(f"Received Dwolla webhook event: {event_topic}, id: {event_id}")
    
    # Handle Dwolla transfer events
    if event_topic == "transfer_completed":
        await handle_dwolla_transfer_completed(db, event_id, event_data)
    elif event_topic == "transfer_failed":
        await handle_dwolla_transfer_failed(db, event_id, event_data)
    elif event_topic == "transfer_cancelled":
        await handle_dwolla_transfer_cancelled(db, event_id, event_data)
    else:
        logger.info(f"Unhandled Dwolla event topic: {event_topic}")
    
    return {"status": "ok"}


async def handle_dwolla_transfer_completed(db: Session, event_id: str, transfer_url: str):
    """Handle Dwolla transfer completed event."""
    try:
        # Extract transfer ID from URL
        transfer_id = transfer_url.split("/")[-1] if transfer_url else event_id
        
        # Find the bill payment or reimbursement payout with this transfer reference
        from app.bills.models import BillPayment
        from app.reimbursements.models import Reimbursement
        
        # Check bill payments
        bill_payment = db.query(BillPayment).filter(
            BillPayment.transfer_ref == transfer_id
        ).first()
        
        if bill_payment:
            bill = db.query(Bill).filter(Bill.id == bill_payment.bill_id).first()
            if bill:
                bill.status = "PAID"
                bill_payment.paid_at = datetime.utcnow()
                db.commit()
                logger.info(f"Bill {bill.id} marked as PAID via Dwolla transfer {transfer_id}")
                return
        
        # Check reimbursements
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.transfer_ref == transfer_id
        ).first()
        
        if reimbursement:
            reimbursement.status = "REIMBURSED"
            reimbursement.reimbursed_at = datetime.utcnow()
            db.commit()
            logger.info(f"Reimbursement {reimbursement.id} marked as REIMBURSED via Dwolla transfer {transfer_id}")
            return
        
        logger.warning(f"No matching bill payment or reimbursement found for transfer {transfer_id}")
        
    except Exception as e:
        logger.exception(f"Error handling Dwolla transfer_completed: {e}")


async def handle_dwolla_transfer_failed(db: Session, event_id: str, transfer_url: str):
    """Handle Dwolla transfer failed event."""
    try:
        transfer_id = transfer_url.split("/")[-1] if transfer_url else event_id
        
        # Find and mark as failed
        from app.bills.models import BillPayment
        from app.reimbursements.models import Reimbursement
        
        bill_payment = db.query(BillPayment).filter(
            BillPayment.transfer_ref == transfer_id
        ).first()
        
        if bill_payment:
            bill = db.query(Bill).filter(Bill.id == bill_payment.bill_id).first()
            if bill:
                bill.status = "ERROR"
                db.commit()
                logger.error(f"Bill {bill.id} transfer failed via Dwolla transfer {transfer_id}")
                return
        
        logger.warning(f"No matching bill payment found for failed transfer {transfer_id}")
        
    except Exception as e:
        logger.exception(f"Error handling Dwolla transfer_failed: {e}")


async def handle_dwolla_transfer_cancelled(db: Session, event_id: str, transfer_url: str):
    """Handle Dwolla transfer cancelled event."""
    try:
        transfer_id = transfer_url.split("/")[-1] if transfer_url else event_id
        
        # Find and mark as cancelled
        from app.bills.models import BillPayment
        
        bill_payment = db.query(BillPayment).filter(
            BillPayment.transfer_ref == transfer_id
        ).first()
        
        if bill_payment:
            bill = db.query(Bill).filter(Bill.id == bill_payment.bill_id).first()
            if bill:
                bill.status = "DRAFT"  # Return to draft for retry
                db.commit()
                logger.info(f"Bill {bill.id} transfer cancelled, returned to DRAFT via Dwolla transfer {transfer_id}")
                return
        
        logger.warning(f"No matching bill payment found for cancelled transfer {transfer_id}")
        
    except Exception as e:
        logger.exception(f"Error handling Dwolla transfer_cancelled: {e}")


@router.post("/didit")
async def didit_webhook(
    request: Request,
    x_didit_signature: str = Header(None, alias="X-Didit-Signature"),
    db: Session = Depends(get_db)
):
    """Handle Didit webhook events for KYC/KYB verification status updates."""

    payload = await request.body()

    # Didit signs webhooks with HMAC-SHA256 of the raw body in X-Didit-Signature,
    # keyed by the webhook secret configured in the Didit dashboard.
    _require_valid_signature("Didit", payload, x_didit_signature, DIDIT_WEBHOOK_SECRET)

    import json
    event = json.loads(payload)
    
    verification_id = event.get("verification_id")
    status = event.get("status")  # "approved", "rejected", "pending"
    external_id = event.get("external_id")
    
    logger.info(f"Received Didit webhook: verification_id={verification_id}, status={status}, external_id={external_id}")
    
    # Find the entity by verification_id or external_id
    from app.entities_rbac.models import Entity
    
    entity = db.query(Entity).filter(
        (Entity.verification_id == verification_id) | (Entity.id == external_id)
    ).first()
    
    if not entity:
        logger.warning(f"Entity not found for Didit verification {verification_id}")
        return {"status": "ok"}
    
    # Update entity onboarding status based on verification result
    if status == "approved":
        entity.onboarding_status = "APPROVED"
        logger.info(f"Entity {entity.id} onboarding approved via Didit verification {verification_id}")
    elif status == "rejected":
        entity.onboarding_status = "SUSPENDED"
        logger.warning(f"Entity {entity.id} onboarding rejected via Didit verification {verification_id}")
    elif status == "pending":
        entity.onboarding_status = "PENDING"
        logger.info(f"Entity {entity.id} onboarding still pending via Didit verification {verification_id}")
    
    db.commit()
    
    return {"status": "ok"}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    """Handle Stripe Issuing webhook events for authorization, hold, and settlement."""
    
    payload = await request.body()
    
    # Verify webhook signature if secret is configured
    if STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid Stripe payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid Stripe signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # For testing without signature verification
        import json
        event = json.loads(payload)
    
    event_type = event.get("type")
    event_data = event.get("data", {}).get("object", {})
    
    logger.info(f"Received Stripe webhook event: {event_type}")
    
    # Handle Stripe Issuing events
    if event_type == "issuing_authorization.created":
        await handle_authorization_created(db, event_data)
    elif event_type == "issuing_authorization.updated":
        await handle_authorization_updated(db, event_data)
    elif event_type == "issuing_transaction.created":
        await handle_transaction_created(db, event_data)
    elif event_type == "issuing_transaction.updated":
        await handle_transaction_updated(db, event_data)
    else:
        logger.info(f"Unhandled Stripe event type: {event_type}")
    
    return {"status": "ok"}


async def handle_authorization_created(db: Session, auth_data: Dict[str, Any]):
    """Handle new authorization request - create a hold in the ledger."""
    try:
        card_id = auth_data.get("card")
        amount = auth_data.get("amount", 0) / 100.0  # Convert from cents
        merchant_data = auth_data.get("merchant_data", {})
        merchant_name = merchant_data.get("name", "Unknown")
        
        # Find the card in our database
        from app.cards.models import Card
        card = db.query(Card).filter(Card.card_token == card_id).first()
        if not card:
            logger.warning(f"Card {card_id} not found for authorization")
            return
        
        # Create a hold in the ledger
        ledger = LedgerClient(db)
        hold = ledger.post_hold(
            entity_id=card.entity_id,
            card_id=card.id,
            amount=amount,
            merchant_name=merchant_name,
            source_event_id=auth_data.get("id")
        )
        
        # Emit pipeline event
        emit_pipeline_event(
            db=db,
            entity_id=card.entity_id,
            transaction_id=hold.id,
            event_type="hold_created",
            source_event_id=auth_data.get("id")
        )
        
        logger.info(f"Created hold {hold.id} for authorization {auth_data.get('id')}")
        
    except Exception as e:
        logger.exception(f"Error handling authorization.created: {e}")


async def handle_authorization_updated(db: Session, auth_data: Dict[str, Any]):
    """Handle authorization updates (approved/declined)."""
    try:
        auth_id = auth_data.get("id")
        approved = auth_data.get("approved", False)
        
        # Find the corresponding hold/transaction
        from app.transactions.models import Transaction
        tx = db.query(Transaction).filter(
            Transaction.source_event_id == auth_id
        ).first()
        
        if not tx:
            logger.warning(f"Transaction not found for authorization {auth_id}")
            return
        
        if approved:
            logger.info(f"Authorization {auth_id} approved for transaction {tx.id}")
        else:
            logger.info(f"Authorization {auth_id} declined for transaction {tx.id}")
            # Could update transaction status here if needed
            
    except Exception as e:
        logger.exception(f"Error handling authorization.updated: {e}")


async def handle_transaction_created(db: Session, tx_data: Dict[str, Any]):
    """Handle new transaction (settlement)."""
    try:
        card_id = tx_data.get("card")
        amount = tx_data.get("amount", 0) / 100.0  # Convert from cents
        merchant_data = tx_data.get("merchant_data", {})
        merchant_name = merchant_data.get("name", "Unknown")
        
        # Find the card in our database
        from app.cards.models import Card
        card = db.query(Card).filter(Card.card_token == card_id).first()
        if not card:
            logger.warning(f"Card {card_id} not found for transaction")
            return
        
        # Find the hold for this transaction
        from app.transactions.models import Transaction
        hold = db.query(Transaction).filter(
            Transaction.card_id == card.id,
            Transaction.state == "HELD",
            Transaction.merchant_name == merchant_name
        ).first()
        
        # Create settlement in the ledger
        ledger = LedgerClient(db)
        if hold:
            settlement = ledger.post_settlement(hold_id=hold.id, amount=amount)
        else:
            # Fallback: create settlement without hold
            settlement = ledger.post_settlement(
                entity_id=card.entity_id,
                card_id=card.id,
                amount=amount,
                merchant_name=merchant_name,
                source_event_id=tx_data.get("id")
            )
        
        # Emit pipeline event
        emit_pipeline_event(
            db=db,
            entity_id=card.entity_id,
            transaction_id=settlement.id,
            event_type="settled",
            source_event_id=tx_data.get("id")
        )
        
        logger.info(f"Created settlement {settlement.id} for transaction {tx_data.get('id')}")
        
        # Trigger categorization job
        from app.transactions.tasks import categorize_transaction
        categorize_transaction.delay(settlement.id)
        
    except Exception as e:
        logger.exception(f"Error handling transaction.created: {e}")


async def handle_transaction_updated(db: Session, tx_data: Dict[str, Any]):
    """Handle transaction updates (refunds, etc.)."""
    try:
        tx_id = tx_data.get("id")
        logger.info(f"Transaction updated: {tx_id}")
        # Handle refunds or other updates if needed
        
    except Exception as e:
        logger.exception(f"Error handling transaction.updated: {e}")
