from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext

router = APIRouter(prefix="/api/ops", tags=["ops"])


class OpsSummaryOut(BaseModel):
    pending_approvals: int
    open_disputes: int
    vendors_sanctions_hit: int
    sync_errors: int
    open_reconciliation_discrepancies: int
    unread_admin_notifications: int


@router.get("/summary", response_model=OpsSummaryOut)
def ops_summary(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """One-screen view of everything in the entity that needs an admin's
    attention right now — the closest thing this app has to an ops console."""
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can view the ops summary")

    from app.approvals.models import Approval, ApprovalState
    from app.disputes.models import CardDispute
    from app.disputes.router import OPEN_STATUSES as OPEN_DISPUTE_STATUSES
    from app.bills.models import Vendor
    from app.accounting.models import SyncQueue
    from app.reconciliation.models import ReconciliationDiscrepancy, ReconciliationRun
    from app.notifications.models import Notification

    entity_id = current_user.active_entity_id

    pending_approvals = db.query(Approval).filter(
        Approval.entity_id == entity_id, Approval.state == ApprovalState.SUBMITTED
    ).count()

    open_disputes = db.query(CardDispute).filter(
        CardDispute.entity_id == entity_id, CardDispute.status.in_(OPEN_DISPUTE_STATUSES)
    ).count()

    vendors_sanctions_hit = db.query(Vendor).filter(
        Vendor.entity_id == entity_id, Vendor.screening_status == "HIT"
    ).count()

    sync_errors = db.query(SyncQueue).filter(
        SyncQueue.entity_id == entity_id, SyncQueue.status == "ERROR"
    ).count()

    open_reconciliation_discrepancies = (
        db.query(ReconciliationDiscrepancy)
        .join(ReconciliationRun, ReconciliationRun.id == ReconciliationDiscrepancy.run_id)
        .filter(ReconciliationRun.entity_id == entity_id, ReconciliationDiscrepancy.resolved.is_(None))
        .count()
    )

    unread_admin_notifications = db.query(Notification).filter(
        Notification.entity_id == entity_id,
        Notification.user_id == current_user.user_id,
        Notification.read.is_(False),
    ).count()

    return {
        "pending_approvals": pending_approvals,
        "open_disputes": open_disputes,
        "vendors_sanctions_hit": vendors_sanctions_hit,
        "sync_errors": sync_errors,
        "open_reconciliation_discrepancies": open_reconciliation_discrepancies,
        "unread_admin_notifications": unread_admin_notifications,
    }


class DiscrepancyResolveIn(BaseModel):
    action: str  # RETRY or ACKNOWLEDGE


@router.post("/reconciliation-discrepancies/{discrepancy_id}/resolve")
def resolve_discrepancy(
    discrepancy_id: str,
    body: DiscrepancyResolveIn,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Act on a reconciliation discrepancy: RETRY resets the underlying bill/
    reimbursement to APPROVED so it can be paid out again (use when the
    provider genuinely failed the transfer); ACKNOWLEDGE just closes it out
    without changing anything (use for a false positive)."""
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can resolve reconciliation discrepancies")

    if body.action not in ("RETRY", "ACKNOWLEDGE"):
        raise HTTPException(status_code=400, detail="action must be RETRY or ACKNOWLEDGE")

    from app.reconciliation.models import ReconciliationDiscrepancy, ReconciliationRun

    discrepancy = (
        db.query(ReconciliationDiscrepancy)
        .join(ReconciliationRun, ReconciliationRun.id == ReconciliationDiscrepancy.run_id)
        .filter(
            ReconciliationDiscrepancy.id == discrepancy_id,
            ReconciliationRun.entity_id == current_user.active_entity_id,
        )
        .first()
    )
    if not discrepancy:
        raise HTTPException(status_code=404, detail="Discrepancy not found")

    if discrepancy.resolved:
        raise HTTPException(status_code=400, detail=f"Discrepancy already resolved ({discrepancy.resolved})")

    if body.action == "RETRY":
        if discrepancy.subject_type == "BILL_PAYMENT":
            from app.bills.models import Bill, BillPayment
            payment = db.query(BillPayment).filter(BillPayment.id == discrepancy.subject_id).first()
            if payment:
                bill = db.query(Bill).filter(Bill.id == payment.bill_id).first()
                if bill and bill.status == "PAID":
                    bill.status = "APPROVED"
        elif discrepancy.subject_type == "REIMBURSEMENT":
            from app.reimbursements.models import Reimbursement
            reimb = db.query(Reimbursement).filter(Reimbursement.id == discrepancy.subject_id).first()
            if reimb and reimb.status == "REIMBURSED":
                reimb.status = "APPROVED"

    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=current_user.active_entity_id,
        user_id=current_user.user_id,
        action="RECONCILIATION_DISCREPANCY_RESOLVED",
        details={
            "discrepancy_id": discrepancy.id,
            "subject_type": discrepancy.subject_type,
            "subject_id": discrepancy.subject_id,
            "resolution": body.action,
        }
    )

    discrepancy.resolved = body.action + "D" if body.action == "ACKNOWLEDGE" else "RETRIED"
    discrepancy.resolved_at = datetime.utcnow()
    discrepancy.resolved_by = current_user.user_id
    db.commit()

    return {"id": discrepancy.id, "resolved": discrepancy.resolved}
