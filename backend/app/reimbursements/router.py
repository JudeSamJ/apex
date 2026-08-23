from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
import uuid

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.reimbursements.models import Reimbursement, ReimbursementLineItem, MileageTrip, TripWaypoint
from app.bills.payment_rail import MockPaymentRailClient
from app.bills.payment_rail import get_payment_rail_client
from app.approvals.engine import ApprovalEngine
from app.idempotency.service import begin_idempotent, complete_idempotent, IdempotencyConflict, IdempotentReplay
from app.money import MoneyOut

router = APIRouter(prefix="/api/reimbursements", tags=["reimbursements"])
payment_rail = get_payment_rail_client()

# Configurable default mileage rate ($0.67 per mile)
DEFAULT_MILEAGE_RATE = Decimal("0.67")

class LineItemIn(BaseModel):
    description: str
    amount: Decimal
    gl_account_id: Optional[str] = None
    receipt_url: Optional[str] = None

class WaypointIn(BaseModel):
    sequence: int
    address: str

class TripIn(BaseModel):
    purpose: str
    total_miles: Decimal
    waypoints: List[WaypointIn]

class ReimbursementCreate(BaseModel):
    type: str  # OUT_OF_POCKET or MILEAGE
    department_id: str
    line_items: Optional[List[LineItemIn]] = None
    trip: Optional[TripIn] = None

class LineItemOut(BaseModel):
    description: str
    amount: MoneyOut
    gl_account_id: Optional[str] = None
    receipt_url: Optional[str] = None

class WaypointOut(BaseModel):
    sequence: int
    address: str

class TripOut(BaseModel):
    purpose: str
    mileage_rate: Decimal
    total_miles: Decimal
    computed_amount: MoneyOut
    waypoints: List[WaypointOut]

class ReimbursementOut(BaseModel):
    id: str
    type: str
    status: str
    total_amount: MoneyOut
    requester_name: str
    department_name: str
    approval_id: Optional[str] = None
    submitted_at: str
    line_items: List[LineItemOut] = []
    trip: Optional[TripOut] = None

@router.post("", response_model=ReimbursementOut)
def create_reimbursement(
    reimb_in: ReimbursementCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()

    if reimb_in.type not in ["OUT_OF_POCKET", "MILEAGE"]:
        raise HTTPException(status_code=400, detail="Invalid reimbursement type")

    # Determine amount & construct sub-objects
    total_amount = Decimal("0.0000")
    line_items_created = []
    trip_created = None

    if reimb_in.type == "OUT_OF_POCKET":
        if not reimb_in.line_items or len(reimb_in.line_items) == 0:
            raise HTTPException(status_code=400, detail="Out of pocket claims must have at least one line item")
        total_amount = sum(item.amount for item in reimb_in.line_items)
    else:
        # MILEAGE
        if not reimb_in.trip:
            raise HTTPException(status_code=400, detail="Mileage claims must have trip details")
        if len(reimb_in.trip.waypoints) == 0:
            raise HTTPException(status_code=400, detail="Mileage trip must have waypoints")
        
        # We can dynamically edit mileage rate per entity, here we use default
        rate = DEFAULT_MILEAGE_RATE
        total_amount = reimb_in.trip.total_miles * rate

    # Create Core Reimbursement Row
    reimb = Reimbursement(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        department_id=reimb_in.department_id,
        user_id=current_user.user_id,
        type=reimb_in.type,
        status="SUBMITTED",
        total_amount=total_amount
    )
    db.add(reimb)
    db.flush()

    # Save sub-objects
    if reimb_in.type == "OUT_OF_POCKET" and reimb_in.line_items:
        for item in reimb_in.line_items:
            li = ReimbursementLineItem(
                entity_id=reimb.entity_id,
                reimbursement_id=reimb.id,
                description=item.description,
                amount=item.amount,
                gl_account_id=item.gl_account_id,
                receipt_url=item.receipt_url
            )
            db.add(li)
            line_items_created.append(li)
    else:
        # Mileage
        t_data = reimb_in.trip
        rate = DEFAULT_MILEAGE_RATE
        trip = MileageTrip(
            id=str(uuid.uuid4()),
            entity_id=reimb.entity_id,
            reimbursement_id=reimb.id,
            purpose=t_data.purpose,
            mileage_rate=rate,
            total_miles=t_data.total_miles,
            computed_amount=total_amount
        )
        db.add(trip)
        db.flush()
        trip_created = trip

        for wp in t_data.waypoints:
            waypoint = TripWaypoint(
                entity_id=reimb.entity_id,
                trip_id=trip.id,
                sequence=wp.sequence,
                address=wp.address
            )
            db.add(waypoint)

    db.flush()

    # Route through Approval Engine
    approval = ApprovalEngine.submit_for_approval(
        db=db,
        approvable_type="REIMBURSEMENT",
        approvable_id=reimb.id,
        entity_id=reimb.entity_id,
        department_id=reimb.department_id,
        amount=reimb.total_amount
    )

    reimb.approval_id = approval.id
    db.commit()
    db.refresh(reimb)

    # Construct Out Payload
    out_lines = [
        {"description": li.description, "amount": li.amount, "gl_account_id": li.gl_account_id, "receipt_url": li.receipt_url}
        for li in line_items_created
    ]

    out_trip = None
    if trip_created:
        out_trip = {
            "purpose": trip_created.purpose,
            "mileage_rate": trip_created.mileage_rate,
            "total_miles": trip_created.total_miles,
            "computed_amount": trip_created.computed_amount,
            "waypoints": [{"sequence": wp.sequence, "address": wp.address} for wp in trip_created.waypoints]
        }

    return {
        "id": reimb.id,
        "type": reimb.type,
        "status": reimb.status,
        "total_amount": reimb.total_amount,
        "requester_name": reimb.user.name,
        "department_name": reimb.department.name,
        "approval_id": reimb.approval_id,
        "submitted_at": reimb.submitted_at.isoformat(),
        "line_items": out_lines,
        "trip": out_trip
    }

@router.get("", response_model=List[ReimbursementOut])
def list_reimbursements(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(Reimbursement).filter(Reimbursement.entity_id == current_user.active_entity_id)

    # Employees can only see their own claims
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        query = query.filter(Reimbursement.user_id == current_user.user_id)

    reimbs = query.all()
    out = []
    for r in reimbs:
        out_lines = [
            {"description": li.description, "amount": li.amount, "gl_account_id": li.gl_account_id, "receipt_url": li.receipt_url}
            for li in r.line_items
        ]
        out_trip = None
        if r.trips:
            trip = r.trips[0]
            out_trip = {
                "purpose": trip.purpose,
                "mileage_rate": trip.mileage_rate,
                "total_miles": trip.total_miles,
                "computed_amount": trip.computed_amount,
                "waypoints": [{"sequence": wp.sequence, "address": wp.address} for wp in trip.waypoints]
            }
        
        out.append({
            "id": r.id,
            "type": r.type,
            "status": r.status,
            "total_amount": r.total_amount,
            "requester_name": r.user.name,
            "department_name": r.department.name,
            "approval_id": r.approval_id,
            "submitted_at": r.submitted_at.isoformat(),
            "line_items": out_lines,
            "trip": out_trip
        })
    return out

@router.post("/{id}/payout")
def payout_reimbursement(
    id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can payout approved reimbursements")

    try:
        idem_record = begin_idempotent(db, idempotency_key, "reimbursements.payout", current_user.active_entity_id)
    except IdempotentReplay as replay:
        return replay.response_body
    except IdempotencyConflict as conflict:
        raise HTTPException(status_code=409, detail=str(conflict))

    reimb = db.query(Reimbursement).filter(
        Reimbursement.id == id,
        Reimbursement.entity_id == current_user.active_entity_id,
        Reimbursement.status == "APPROVED"
    ).first()

    if not reimb:
        raise HTTPException(status_code=404, detail="Approved reimbursement claim not found")

    # Call payment rail to mock ACH transfer
    transfer_ref = payment_rail.initiate_transfer("personal_bank_account_ref", reimb.total_amount)

    gl_acc_id = reimb.line_items[0].gl_account_id if (reimb.line_items and reimb.line_items[0].gl_account_id) else None
    if not gl_acc_id:
        from app.accounting.router import get_auto_coded_gl_account
        gl_acc_id = get_auto_coded_gl_account(db, reimb.entity_id, "DEPARTMENT", reimb.department_id)

    reimb.status = "REIMBURSED"
    reimb.reimbursed_at = datetime.utcnow()
    reimb.transfer_ref = transfer_ref
    
    if gl_acc_id:
        from app.accounting.router import push_to_sync_queue
        push_to_sync_queue(db, reimb.entity_id, "REIMBURSEMENT", reimb.id, gl_acc_id)

    result = {
        "message": "Reimbursement payout initiated",
        "transfer_ref": transfer_ref,
        "status": reimb.status
    }
    complete_idempotent(idem_record, 200, result)
    db.commit()

    return result
