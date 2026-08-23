import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app.bills.payment_rail import get_payment_rail_client
from app.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy

logger = logging.getLogger(__name__)

# Local status a paid/reimbursed record is expected to map to on the provider side.
EXPECTED_PROVIDER_STATUS = "processed"


def run_payment_rail_reconciliation(db: Session, entity_id: str) -> ReconciliationRun:
    """Compare every bank-transfer bill payment and reimbursement payout for
    an entity against the payment rail's current view of that transfer,
    flagging anything where the two disagree (e.g. we think a bill is PAID
    but the rail says the transfer failed or was cancelled).

    Runs synchronously — reconciliation at this scale is a lightweight,
    on-demand admin action, not a scheduled bulk job, so no queue is needed.
    """
    from app.bills.models import Bill, BillPayment
    from app.reimbursements.models import Reimbursement

    run = ReconciliationRun(entity_id=entity_id, provider="PAYMENT_RAIL", status="RUNNING")
    db.add(run)
    db.flush()

    payment_rail = get_payment_rail_client()
    checked = 0
    discrepancies = 0

    try:
        bill_payments = (
            db.query(BillPayment)
            .join(Bill, Bill.id == BillPayment.bill_id)
            .filter(Bill.entity_id == entity_id, BillPayment.transfer_ref.isnot(None))
            .all()
        )
        for payment in bill_payments:
            bill = db.query(Bill).filter(Bill.id == payment.bill_id).first()
            checked += 1
            provider_status = payment_rail.get_transfer_status(payment.transfer_ref)
            if bill.status == "PAID" and provider_status != EXPECTED_PROVIDER_STATUS:
                db.add(ReconciliationDiscrepancy(
                    run_id=run.id,
                    subject_type="BILL_PAYMENT",
                    subject_id=payment.id,
                    transfer_ref=payment.transfer_ref,
                    local_status=bill.status,
                    provider_status=provider_status,
                    amount=bill.total_amount,
                ))
                discrepancies += 1

        reimbursements = (
            db.query(Reimbursement)
            .filter(Reimbursement.entity_id == entity_id, Reimbursement.transfer_ref.isnot(None))
            .all()
        )
        for reimb in reimbursements:
            checked += 1
            provider_status = payment_rail.get_transfer_status(reimb.transfer_ref)
            if reimb.status == "REIMBURSED" and provider_status != EXPECTED_PROVIDER_STATUS:
                db.add(ReconciliationDiscrepancy(
                    run_id=run.id,
                    subject_type="REIMBURSEMENT",
                    subject_id=reimb.id,
                    transfer_ref=reimb.transfer_ref,
                    local_status=reimb.status,
                    provider_status=provider_status,
                    amount=reimb.total_amount,
                ))
                discrepancies += 1

        run.status = "COMPLETED"
        run.checked_count = checked
        run.discrepancy_count = discrepancies
        run.completed_at = datetime.utcnow()

        if discrepancies:
            logger.warning(
                f"Reconciliation run {run.id} for entity {entity_id} found "
                f"{discrepancies} discrepancy(ies) across {checked} transfer(s)"
            )

    except Exception as e:
        logger.exception(f"Reconciliation run {run.id} for entity {entity_id} failed: {e}")
        run.status = "FAILED"
        run.error_message = str(e)[:1000]
        run.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(run)
    return run
