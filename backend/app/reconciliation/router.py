from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy
from app.reconciliation.service import run_payment_rail_reconciliation

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


class RunOut(BaseModel):
    id: str
    provider: str
    status: str
    checked_count: int
    discrepancy_count: int
    error_message: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None


class DiscrepancyOut(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    transfer_ref: str
    local_status: str
    provider_status: str
    amount: Optional[float] = None
    resolved: Optional[str] = None
    created_at: str


def _run_out(r: ReconciliationRun) -> dict:
    return {
        "id": r.id,
        "provider": r.provider,
        "status": r.status,
        "checked_count": r.checked_count,
        "discrepancy_count": r.discrepancy_count,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat(),
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def _discrepancy_out(d: ReconciliationDiscrepancy) -> dict:
    return {
        "id": d.id,
        "subject_type": d.subject_type,
        "subject_id": d.subject_id,
        "transfer_ref": d.transfer_ref,
        "local_status": d.local_status,
        "provider_status": d.provider_status,
        "amount": float(d.amount) if d.amount is not None else None,
        "resolved": d.resolved,
        "created_at": d.created_at.isoformat(),
    }


@router.post("/run", response_model=RunOut)
def trigger_reconciliation(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can run reconciliation")

    run = run_payment_rail_reconciliation(db, current_user.active_entity_id)
    return _run_out(run)


@router.get("/runs", response_model=List[RunOut])
def list_runs(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ReconciliationRun)
        .filter(ReconciliationRun.entity_id == current_user.active_entity_id)
        .order_by(ReconciliationRun.started_at.desc())
        .all()
    )
    return [_run_out(r) for r in rows]


@router.get("/runs/{run_id}/discrepancies", response_model=List[DiscrepancyOut])
def list_discrepancies(
    run_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    run = db.query(ReconciliationRun).filter(
        ReconciliationRun.id == run_id, ReconciliationRun.entity_id == current_user.active_entity_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")

    rows = (
        db.query(ReconciliationDiscrepancy)
        .filter(ReconciliationDiscrepancy.run_id == run_id)
        .order_by(ReconciliationDiscrepancy.created_at.desc())
        .all()
    )
    return [_discrepancy_out(d) for d in rows]
