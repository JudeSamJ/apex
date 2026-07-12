from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.jobs.models import BackgroundJob

router = APIRouter(prefix="/api/reporting/background-jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

class BackgroundJobOut(BaseModel):
    id: str
    job_type: str
    source_event_id: str
    status: str
    retries: int
    max_retries: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

@router.get("", response_model=List[BackgroundJobOut])
def list_background_jobs(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Background jobs monitoring is restricted to Admins")

    jobs = db.query(BackgroundJob).filter(
        BackgroundJob.entity_id == current_user.active_entity_id
    ).order_by(BackgroundJob.updated_at.desc()).all()

    out = []
    for j in jobs:
        out.append({
            "id": j.id,
            "job_type": j.job_type,
            "source_event_id": j.source_event_id,
            "status": j.status,
            "retries": j.retries,
            "max_retries": j.max_retries,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat(),
            "updated_at": j.updated_at.isoformat()
        })
    return out

@router.post("/{job_id}/retry")
def retry_background_job(
    job_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can retry background jobs")

    job = db.query(BackgroundJob).filter(
        BackgroundJob.id == job_id,
        BackgroundJob.entity_id == current_user.active_entity_id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Background job record not found")

    job.status = "PENDING"
    job.error_message = None
    db.commit()

    # Re-dispatch job synchronously or via celery
    if job.job_type == "SETTLEMENT":
        from app.transactions.tasks import process_settlement
        from app.transactions.models import Transaction
        tx = db.query(Transaction).filter(Transaction.id == job.source_event_id).first()
        if tx:
            process_settlement.delay(tx.id, float(tx.amount))
    elif job.job_type == "ERP_SYNC":
        from app.accounting.models import SyncQueue
        item = db.query(SyncQueue).filter(SyncQueue.id == job.source_event_id).first()
        if item:
            item.status = "SYNC_READY"
            item.error_message = None
            db.commit()
    elif job.job_type == "INSIGHT_DETECTION":
        from app.insights.router import run_insights_job_internal
        run_insights_job_internal(db, job.entity_id)
    elif job.job_type == "PAYMENT_RAIL":
        # Check bills or payments status
        from app.bills.router import check_pending_transfers_internal
        check_pending_transfers_internal(db, job.entity_id)

    db.refresh(job)
    return {"message": "Job re-dispatched successfully", "status": job.status}
