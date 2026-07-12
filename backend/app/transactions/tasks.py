from decimal import Decimal
from app.celery_app import celery
from app.database import SessionLocal
from app.transactions.models import Transaction
from app.ledger.client import LedgerClient
import logging

logger = logging.getLogger(__name__)

# Basic rules-based categorization mapping MCC to categories
MCC_CATEGORIES = {
    "5812": "Food & Dining",
    "5411": "Groceries",
    "4121": "Travel & Transportation",
    "4816": "Software & SaaS",
    "7372": "Software & SaaS",
    "3000": "Travel & Transportation",
    "5311": "Shopping"
}

def auto_categorize(mcc: str, merchant_name: str) -> str:
    # Rules-based categorization
    mcc_match = MCC_CATEGORIES.get(mcc)
    if mcc_match:
        return mcc_match
    
    # Fuzzy keyword matching on merchant name
    name_lower = merchant_name.lower()
    if "uber" in name_lower or "lyft" in name_lower or "delta" in name_lower:
        return "Travel & Transportation"
    if "aws" in name_lower or "google cloud" in name_lower or "github" in name_lower or "slack" in name_lower:
        return "Software & SaaS"
    if "restaurant" in name_lower or "cafe" in name_lower or "starbucks" in name_lower:
        return "Food & Dining"
        
    return "General Spend"

@celery.task(name="app.transactions.tasks.process_settlement")
def process_settlement(transaction_id: str, settled_amount_float: float):
    logger.info(f"Processing settlement for transaction {transaction_id} with amount {settled_amount_float}")
    db = SessionLocal()
    
    # 1. Fetch transaction
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        logger.error(f"Transaction {transaction_id} not found")
        db.close()
        return False

    # 2. Get or create BackgroundJob tracking row
    from app.jobs.models import BackgroundJob
    job = db.query(BackgroundJob).filter(
        BackgroundJob.job_type == "SETTLEMENT",
        BackgroundJob.source_event_id == transaction_id
    ).first()
    if not job:
        job = BackgroundJob(
            entity_id=tx.entity_id,
            job_type="SETTLEMENT",
            source_event_id=transaction_id,
            status="RUNNING"
        )
        db.add(job)
        db.flush()
    else:
        job.status = "RUNNING"
        db.flush()

    try:
        if tx.status != "HELD":
            logger.warning(f"Transaction {transaction_id} is in status {tx.status}, expected HELD. Skipping.")
            job.status = "COMPLETED"
            db.commit()
            return False

        settled_amount = Decimal(str(settled_amount_float))
        
        # Post to double-entry ledger
        idempotency_key = f"settle_{transaction_id}"
        LedgerClient.post_settlement(
            db=db,
            transaction_id=transaction_id,
            amount=settled_amount,
            idempotency_key=idempotency_key,
            source_event_id=transaction_id
        )

        # Categorize
        category = auto_categorize(tx.merchant_mcc, tx.merchant_name)

        # Update transaction
        tx.amount = settled_amount
        tx.status = "SETTLED"
        tx.category = category

        # Resolve default GL account mapping by MCC
        from app.accounting.router import get_auto_coded_gl_account, push_to_sync_queue
        gl_acc_id = get_auto_coded_gl_account(db, tx.entity_id, "MCC", tx.merchant_mcc)
        if gl_acc_id:
            tx.gl_account_id = gl_acc_id
            # Push to sync queue immediately
            push_to_sync_queue(db, tx.entity_id, "TRANSACTION", tx.id, gl_acc_id)

        job.status = "COMPLETED"
        job.error_message = None
        db.commit()
        logger.info(f"Transaction {transaction_id} settled and categorized as {category}")
        return True
    except Exception as e:
        db.rollback()
        job.retries += 1
        job.status = "FAILED"
        job.error_message = str(e)
        db.commit()
        logger.exception(f"Error processing settlement for transaction {transaction_id}")
        raise e
    finally:
        db.close()
