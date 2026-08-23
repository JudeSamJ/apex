import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.tax_reporting.service import get_1099_nec_summary

router = APIRouter(prefix="/api/tax-reporting", tags=["tax-reporting"])


class NecSummaryOut(BaseModel):
    vendor_id: str
    vendor_name: str
    tax_id: Optional[str] = None
    tax_address: Optional[str] = None
    total_paid: float
    payment_count: int
    reportable: bool


@router.get("/1099-nec/{year}", response_model=List[NecSummaryOut])
def get_1099_nec_report(
    year: int,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Only admins/bookkeepers can view tax reports")

    return get_1099_nec_summary(db, current_user.active_entity_id, year)


@router.get("/1099-nec/{year}/export.csv")
def export_1099_nec_csv(
    year: int,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Only admins/bookkeepers can export tax reports")

    rows = get_1099_nec_summary(db, current_user.active_entity_id, year)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Vendor Name", "TIN", "Address", "Tax Year",
        "Box 1 - Nonemployee Compensation", "Payment Count"
    ])
    for row in rows:
        writer.writerow([
            row["vendor_name"],
            row["tax_id"] or "TIN_REQUIRED",
            row["tax_address"] or "ADDRESS_REQUIRED",
            year,
            f"{row['total_paid']:.2f}",
            row["payment_count"],
        ])
    buffer.seek(0)

    filename = f"1099-nec_{year}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
