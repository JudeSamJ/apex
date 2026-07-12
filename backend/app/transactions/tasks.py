from decimal import Decimal
from app.celery_app import celery
from app.database import SessionLocal
from app.transactions.models import Transaction
from app.ledger.client import LedgerClient
from app.transactions.pipeline_events import emit_pipeline_event
import logging

logger = logging.getLogger(__name__)

MCC_CATEGORIES = {
    "5812": "Food & Dining",
    "5411": "Groceries",
    "4121": "Travel & Transportation",
    "4816": "Software & SaaS",
    "7372": "Software & SaaS",
    "3000": "Travel & Transportation",
    "5311": "Shopping",
}


def auto_categorize(mcc: str, merchant_name: str) -> str:
    mcc_match = MCC_CATEGORIES.get(mcc)
    if mcc_match:
        return mcc_match

    name_lower = merchant_name.lower()
    if "uber" in name_lower or "lyft" in name_lower or "delta" in name_lower:
        return "Travel & Transportation"
    if "aws" in name_lower or "google cloud" in name_lower or "github" in name_lower or "slack" in name_lower:
        return "Software & SaaS"
    if "restaurant" in name_lower or "cafe" in name_lower or "starbucks" in name_lower:
        return "Food & Dining"

    return "General Spend"


def _get_or_create_job(db, tx, job_type: str):
    from app.jobs.models import BackgroundJob
    job = db.query(BackgroundJob).filter(
        BackgroundJob.job_type == job_type,
        BackgroundJob.source_event_id == tx.id,
    ).first()
    if not job:
        job = BackgroundJob(
            entity_id=tx.entity_id,
            job_type=job_type,
            source_event_id=tx.id,
            status="RUNNING",
        )
        db.add(job)
        db.flush()
    else:
        job.status = "RUNNING"
        db.flush()
    return job


def _mark_job_failed(db, job, error: Exception):
    job.retries += 1
    job.status = "FAILED"
    job.error_message = str(error)
    db.commit()


@celery.task(name="app.transactions.tasks.process_settlement")
def process_settlement(transaction_id: str, settled_amount_float: float):
    logger.info("Processing settlement for transaction %s", transaction_id)
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            logger.error("Transaction %s not found", transaction_id)
            return False

        job = _get_or_create_job(db, tx, "SETTLEMENT")

        if tx.status != "HELD":
            logger.warning("Transaction %s status %s, expected HELD", transaction_id, tx.status)
            job.status = "COMPLETED"
            db.commit()
            return False

        settled_amount = Decimal(str(settled_amount_float))
        idempotency_key = f"settle_{transaction_id}"
        LedgerClient.post_settlement(
            db=db,
            transaction_id=transaction_id,
            amount=settled_amount,
            idempotency_key=idempotency_key,
            source_event_id=transaction_id,
        )

        tx.amount = settled_amount
        tx.status = "SETTLED"
        emit_pipeline_event(db, tx.entity_id, tx.id, "settled", transaction_id)
        job.status = "COMPLETED"
        job.error_message = None
        db.commit()

        process_categorization.delay(transaction_id)
        return True
    except Exception as e:
        db.rollback()
        if "job" in dir() and job:
            _mark_job_failed(db, job, e)
        logger.exception("Settlement failed for %s", transaction_id)
        raise
    finally:
        db.close()


@celery.task(name="app.transactions.tasks.process_categorization")
def process_categorization(transaction_id: str):
    logger.info("Categorizing transaction %s", transaction_id)
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx or tx.status != "SETTLED":
            return False

        job = _get_or_create_job(db, tx, "CATEGORIZATION")
        if tx.category:
            job.status = "COMPLETED"
            db.commit()
            route_transaction_approval.delay(transaction_id)
            return True

        tx.category = auto_categorize(tx.merchant_mcc, tx.merchant_name)
        emit_pipeline_event(db, tx.entity_id, tx.id, "categorized", transaction_id)
        job.status = "COMPLETED"
        job.error_message = None
        db.commit()

        route_transaction_approval.delay(transaction_id)
        return True
    except Exception as e:
        db.rollback()
        if "job" in dir() and job:
            _mark_job_failed(db, job, e)
        logger.exception("Categorization failed for %s", transaction_id)
        raise
    finally:
        db.close()


@celery.task(name="app.transactions.tasks.route_transaction_approval")
def route_transaction_approval(transaction_id: str):
    logger.info("Routing approval for transaction %s", transaction_id)
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx or tx.status != "SETTLED":
            return False

        job = _get_or_create_job(db, tx, "APPROVAL_ROUTING")

        from app.cards.models import Card
        card = db.query(Card).filter(Card.id == tx.card_id).first()
        needs_approval = False
        if card and card.spend_program and card.spend_program.approval_threshold is not None:
            needs_approval = tx.amount >= card.spend_program.approval_threshold

        if needs_approval:
            from app.approvals.engine import ApprovalEngine
            ApprovalEngine.submit_for_approval(
                db=db,
                approvable_type="TRANSACTION",
                approvable_id=tx.id,
                entity_id=tx.entity_id,
                department_id=tx.department_id,
                amount=tx.amount,
            )
            emit_pipeline_event(db, tx.entity_id, tx.id, "approval_required", transaction_id)

        job.status = "COMPLETED"
        job.error_message = None
        db.commit()

        process_gl_coding.delay(transaction_id)
        return True
    except Exception as e:
        db.rollback()
        if "job" in dir() and job:
            _mark_job_failed(db, job, e)
        logger.exception("Approval routing failed for %s", transaction_id)
        raise
    finally:
        db.close()


@celery.task(name="app.transactions.tasks.process_gl_coding")
def process_gl_coding(transaction_id: str):
    logger.info("GL coding transaction %s", transaction_id)
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx or tx.status != "SETTLED":
            return False

        job = _get_or_create_job(db, tx, "GL_CODING")
        if tx.gl_account_id:
            job.status = "COMPLETED"
            db.commit()
            push_sync_queue_task.delay(transaction_id)
            return True

        from app.accounting.router import get_auto_coded_gl_account
        gl_acc_id = get_auto_coded_gl_account(db, tx.entity_id, "MCC", tx.merchant_mcc)
        if gl_acc_id:
            tx.gl_account_id = gl_acc_id
            emit_pipeline_event(db, tx.entity_id, tx.id, "gl_coded", transaction_id)

        job.status = "COMPLETED"
        job.error_message = None
        db.commit()

        if gl_acc_id:
            push_sync_queue_task.delay(transaction_id)
        return True
    except Exception as e:
        db.rollback()
        if "job" in dir() and job:
            _mark_job_failed(db, job, e)
        logger.exception("GL coding failed for %s", transaction_id)
        raise
    finally:
        db.close()


@celery.task(name="app.transactions.tasks.push_sync_queue_task")
def push_sync_queue_task(transaction_id: str):
    logger.info("Pushing transaction %s to sync queue", transaction_id)
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx or not tx.gl_account_id:
            return False

        job = _get_or_create_job(db, tx, "SYNC_QUEUE_PUSH")
        from app.accounting.router import push_to_sync_queue
        push_to_sync_queue(db, tx.entity_id, "TRANSACTION", tx.id, tx.gl_account_id)
        emit_pipeline_event(db, tx.entity_id, tx.id, "sync_ready", transaction_id)

        job.status = "COMPLETED"
        job.error_message = None
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        if "job" in dir() and job:
            _mark_job_failed(db, job, e)
        logger.exception("Sync queue push failed for %s", transaction_id)
        raise
    finally:
        db.close()
