from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.screening.service import screen_subject
from app.screening.models import SanctionsScreening

router = APIRouter(prefix="/api/screening", tags=["screening"])


class ScreeningOut(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    subject_name: str
    provider: str
    status: str
    match_details: Optional[Any] = None
    created_at: str


def _to_out(row: SanctionsScreening) -> dict:
    return {
        "id": row.id,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_name": row.subject_name,
        "provider": row.provider,
        "status": row.status,
        "match_details": row.match_details,
        "created_at": row.created_at.isoformat(),
    }


@router.get("", response_model=List[ScreeningOut])
def list_screenings(
    status_filter: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """List sanctions screening records for the active entity and its vendors."""
    from app.bills.models import Vendor

    vendor_ids = [
        v.id for v in db.query(Vendor.id).filter(Vendor.entity_id == current_user.active_entity_id).all()
    ]

    query = db.query(SanctionsScreening).filter(
        (
            (SanctionsScreening.subject_type == "ENTITY")
            & (SanctionsScreening.subject_id == current_user.active_entity_id)
        )
        | ((SanctionsScreening.subject_type == "VENDOR") & (SanctionsScreening.subject_id.in_(vendor_ids)))
    )
    if status_filter:
        query = query.filter(SanctionsScreening.status == status_filter)

    rows = query.order_by(SanctionsScreening.created_at.desc()).all()
    return [_to_out(r) for r in rows]


@router.post("/rescreen/vendor/{vendor_id}", response_model=ScreeningOut)
def rescreen_vendor(
    vendor_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Admin-triggered manual re-screen of a vendor, e.g. after a review or a watchlist update."""
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can trigger a re-screen")

    from app.bills.models import Vendor

    vendor = db.query(Vendor).filter(
        Vendor.id == vendor_id, Vendor.entity_id == current_user.active_entity_id
    ).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    record = screen_subject(db, "VENDOR", vendor.id, vendor.name)
    vendor.screening_status = record.status
    db.commit()
    db.refresh(record)
    return _to_out(record)
