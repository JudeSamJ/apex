from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
import uuid

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.bills.models import Vendor, VendorContact, VendorBankAccount, Bill, BillLineItem, BillPayment
from app.bills.payment_rail import MockPaymentRailClient
from app.approvals.engine import ApprovalEngine
from app.ledger.client import LedgerClient
from app.cards.models import Card
from app.bills.payment_rail import get_payment_rail_client
from app.idempotency.service import begin_idempotent, complete_idempotent, IdempotencyConflict, IdempotentReplay
from app.screening.service import screen_subject

router = APIRouter(prefix="/api/bills", tags=["bills"])
payment_rail = get_payment_rail_client()

class VendorCreate(BaseModel):
    name: str
    email: str
    masked_bank_account: str

class VendorOut(BaseModel):
    id: str
    name: str

class LineItemIn(BaseModel):
    description: str
    amount: Decimal
    gl_account_id: Optional[str] = None

class BillCreate(BaseModel):
    department_id: str
    vendor_id: str
    due_date: str  # YYYY-MM-DD
    payment_method: str  # CARD or BANK_TRANSFER
    line_items: List[LineItemIn]

class BillLineItemOut(BaseModel):
    description: str
    amount: Decimal
    gl_account_id: Optional[str] = None

class BillOut(BaseModel):
    id: str
    department_name: str
    vendor_name: str
    status: str
    due_date: str
    total_amount: Decimal
    payment_method: str
    approval_id: Optional[str] = None
    line_items: List[BillLineItemOut]

def is_fuzzy_match(name1: str, name2: str) -> bool:
    n1 = "".join(name1.lower().split())
    n2 = "".join(name2.lower().split())
    return (n1 in n2) or (n2 in n1)

@router.post("/vendors", response_model=VendorOut)
def create_vendor(
    vendor_in: VendorCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    
    # 1. Fuzzy match duplicate vendor check
    existing_vendors = db.query(Vendor).filter(Vendor.entity_id == current_user.active_entity_id).all()
    for v in existing_vendors:
        if is_fuzzy_match(v.name, vendor_in.name):
            # Vendor already exists (fuzzy matched), reuse it
            return v

    # Create new vendor
    vendor = Vendor(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        name=vendor_in.name
    )
    db.add(vendor)
    db.flush()

    # AML/OFAC sanctions screening on the vendor name before any bill can be paid to it
    screening = screen_subject(db, "VENDOR", vendor.id, vendor.name)
    vendor.screening_status = screening.status
    if screening.status == "HIT":
        from app.notifications.service import notify_users_with_role
        notify_users_with_role(
            db=db,
            entity_id=current_user.active_entity_id,
            role_id="ADMIN",
            type="SANCTIONS_HIT",
            title=f"Vendor '{vendor.name}' flagged by sanctions screening",
            body="This vendor cannot be paid until an admin reviews and clears the screening result.",
            send_email=True,
        )

    contact = VendorContact(
        entity_id=current_user.active_entity_id,
        vendor_id=vendor.id,
        name=vendor_in.name + " Contact",
        email=vendor_in.email
    )
    db.add(contact)

    bank = VendorBankAccount(
        entity_id=current_user.active_entity_id,
        vendor_id=vendor.id,
        masked_account_ref=vendor_in.masked_bank_account
    )
    db.add(bank)
    db.commit()
    db.refresh(vendor)
    return vendor

@router.get("/vendors", response_model=List[VendorOut])
def list_vendors(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return db.query(Vendor).filter(Vendor.entity_id == current_user.active_entity_id).all()

@router.post("", response_model=BillOut)
def create_bill(
    bill_in: BillCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    from app.rate_limit import check_rate_limit
    check_rate_limit(user_id=current_user.user_id, endpoint="create_bill")
    
    if len(bill_in.line_items) == 0:
        raise HTTPException(status_code=400, detail="A bill must have at least one line item")

    if bill_in.payment_method not in ["CARD", "BANK_TRANSFER"]:
        raise HTTPException(status_code=400, detail="Invalid payment method")

    # Verify Vendor exists
    vendor = db.query(Vendor).filter(
        Vendor.id == bill_in.vendor_id,
        Vendor.entity_id == current_user.active_entity_id
    ).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    total_amount = sum(item.amount for item in bill_in.line_items)

    bill = Bill(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        department_id=bill_in.department_id,
        vendor_id=bill_in.vendor_id,
        status="DRAFT",
        due_date=datetime.strptime(bill_in.due_date, "%Y-%m-%d"),
        total_amount=total_amount,
        payment_method=bill_in.payment_method
    )
    db.add(bill)
    db.flush()

    for item in bill_in.line_items:
        li = BillLineItem(
            entity_id=bill.entity_id,
            bill_id=bill.id,
            description=item.description,
            amount=item.amount,
            gl_account_id=item.gl_account_id
        )
        db.add(li)
    
    db.commit()
    db.refresh(bill)

    return {
        "id": bill.id,
        "department_name": bill.department.name,
        "vendor_name": bill.vendor.name,
        "status": bill.status,
        "due_date": bill.due_date.strftime("%Y-%m-%d"),
        "total_amount": bill.total_amount,
        "payment_method": bill.payment_method,
        "line_items": [
            {"description": li.description, "amount": li.amount, "gl_account_id": li.gl_account_id}
            for li in bill.line_items
        ]
    }

@router.get("", response_model=List[BillOut])
def list_bills(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(Bill).filter(Bill.entity_id == current_user.active_entity_id)
    
    # Non-admins can only see bills for their department
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        if current_user.accessible_departments:
            query = query.filter(Bill.department_id.in_(current_user.accessible_departments))
        else:
            query = query.filter(Bill.id == "") # Return empty

    bills = query.all()
    out = []
    for b in bills:
        out.append({
            "id": b.id,
            "department_name": b.department.name,
            "vendor_name": b.vendor.name,
            "status": b.status,
            "due_date": b.due_date.strftime("%Y-%m-%d"),
            "total_amount": b.total_amount,
            "payment_method": b.payment_method,
            "approval_id": b.approval_id,
            "line_items": [
                {"description": li.description, "amount": li.amount, "gl_account_id": li.gl_account_id}
                for li in b.line_items
            ]
        })
    return out

@router.post("/{bill_id}/submit")
def submit_bill(
    bill_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.entity_id == current_user.active_entity_id,
        Bill.status == "DRAFT"
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Draft bill not found")

    # Start approval workflow
    approval = ApprovalEngine.submit_for_approval(
        db=db,
        approvable_type="BILL",
        approvable_id=bill.id,
        entity_id=bill.entity_id,
        department_id=bill.department_id,
        amount=bill.total_amount
    )

    bill.status = "PENDING_APPROVAL"
    bill.approval_id = approval.id
    db.commit()

    return {"message": "Bill submitted for approval", "approval_id": approval.id}

@router.post("/{bill_id}/pay")
def pay_bill(
    bill_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()

    try:
        idem_record = begin_idempotent(db, idempotency_key, "bills.pay", current_user.active_entity_id)
    except IdempotentReplay as replay:
        return replay.response_body
    except IdempotencyConflict as conflict:
        raise HTTPException(status_code=409, detail=str(conflict))

    # Fetch bill
    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.entity_id == current_user.active_entity_id,
        Bill.status == "APPROVED"
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Approved bill not found")

    vendor = db.query(Vendor).filter(Vendor.id == bill.vendor_id).first()
    if vendor and vendor.screening_status == "HIT":
        raise HTTPException(
            status_code=403,
            detail="Vendor is flagged by sanctions screening and cannot be paid until cleared by an admin"
        )

    payment_id = str(uuid.uuid4())

    if bill.payment_method == "CARD":
        # Find first active card in the bill's department
        card = db.query(Card).filter(
            Card.department_id == bill.department_id,
            Card.status == "ACTIVE"
        ).first()
        
        if not card:
            # Fallback to any card in the entity
            card = db.query(Card).filter(
                Card.entity_id == bill.entity_id,
                Card.status == "ACTIVE"
            ).first()

        if not card:
            raise HTTPException(status_code=400, detail="No active corporate card found to charge this bill")

        # Double entry posting: Card Pay is settled immediately
        transaction_id = str(uuid.uuid4())
        
        # 1. Post hold
        LedgerClient.post_hold(
            db=db,
            entity_id=bill.entity_id,
            department_id=bill.department_id,
            card_id=card.id,
            transaction_id=transaction_id,
            amount=bill.total_amount,
            currency="USD",
            idempotency_key=f"bill_hold_{bill.id}",
            source_event_id=bill.id
        )
        
        # 2. Post settlement
        LedgerClient.post_settlement(
            db=db,
            transaction_id=transaction_id,
            amount=bill.total_amount,
            idempotency_key=f"bill_settle_{bill.id}",
            source_event_id=bill.id
        )

        payment = BillPayment(
            id=payment_id,
            entity_id=bill.entity_id,
            bill_id=bill.id,
            transaction_id=transaction_id
        )
        db.add(payment)

    else:
        # Bank transfer
        bank_account = db.query(VendorBankAccount).filter(VendorBankAccount.vendor_id == bill.vendor_id).first()
        masked_ref = bank_account.masked_account_ref if bank_account else "unknown"
        
        transfer_ref = payment_rail.initiate_transfer(masked_ref, bill.total_amount)
        
        payment = BillPayment(
            id=payment_id,
            entity_id=bill.entity_id,
            bill_id=bill.id,
            transfer_ref=transfer_ref
        )
        db.add(payment)

    gl_acc_id = bill.line_items[0].gl_account_id if (bill.line_items and bill.line_items[0].gl_account_id) else None
    if not gl_acc_id:
        from app.accounting.router import get_auto_coded_gl_account
        gl_acc_id = get_auto_coded_gl_account(db, bill.entity_id, "VENDOR", bill.vendor_id)

    bill.status = "PAID"
    if gl_acc_id:
        from app.accounting.router import push_to_sync_queue
        push_to_sync_queue(db, bill.entity_id, "BILL", bill.id, gl_acc_id)

    result = {"message": "Bill paid successfully", "payment_id": payment_id}
    complete_idempotent(idem_record, 200, result)
    db.commit()
    return result

@router.post("/{bill_id}/void")
def void_bill(
    bill_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.entity_id == current_user.active_entity_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if bill.status == "VOID":
        raise HTTPException(status_code=400, detail="Bill is already void")

    # If already PAID via card, reverse the ledger entry
    if bill.status == "PAID":
        for payment in bill.payments:
            if payment.transaction_id:
                LedgerClient.post_reversal(
                    db=db,
                    transaction_id=payment.transaction_id,
                    idempotency_key=f"bill_reverse_{bill.id}",
                    source_event_id=bill.id
                )

    bill.status = "VOID"
    db.commit()
    return {"message": "Bill voided successfully"}

class PaymentRailWebhook(BaseModel):
    type: str
    transfer_ref: Optional[str] = None
    data: Optional[dict] = None

@router.post("/webhooks/payment-rail")
def payment_rail_webhook(webhook: PaymentRailWebhook, db: Session = Depends(get_db)):
    ref = webhook.transfer_ref
    if not ref and webhook.data and "object" in webhook.data and "id" in webhook.data["object"]:
        ref = webhook.data["object"]["id"]
        
    if not ref:
        raise HTTPException(status_code=400, detail="Missing transfer_ref in webhook payload")
        
    # Check bills
    payment = db.query(BillPayment).filter(BillPayment.transfer_ref == ref).first()
    if payment:
        bill = payment.bill
        from app.audit_logs.router import log_audit_action
        if webhook.type in ["transfer.completed", "payment_intent.succeeded"]:
            bill.status = "PAID"
            log_audit_action(
                db=db,
                entity_id=bill.entity_id,
                user_id=None,
                action="BILL_PAID",
                details={"bill_id": bill.id, "transfer_ref": ref}
            )
        elif webhook.type in ["transfer.failed", "transfer.reversed", "payment_intent.payment_failed"]:
            bill.status = "APPROVED"
            log_audit_action(
                db=db,
                entity_id=bill.entity_id,
                user_id=None,
                action="BILL_PAYMENT_FAILED",
                details={"bill_id": bill.id, "transfer_ref": ref, "error": "Webhook failure event"}
            )
        db.commit()
        return {"status": "success", "mapped": "bill"}

    # Check reimbursements
    from app.reimbursements.models import Reimbursement
    reimb = db.query(Reimbursement).filter(Reimbursement.transfer_ref == ref).first()
    if reimb:
        from app.audit_logs.router import log_audit_action
        if webhook.type in ["transfer.completed", "payment_intent.succeeded"]:
            reimb.status = "REIMBURSED"
            log_audit_action(
                db=db,
                entity_id=reimb.entity_id,
                user_id=None,
                action="REIMBURSEMENT_PAID",
                details={"reimbursement_id": reimb.id, "transfer_ref": ref}
            )
        elif webhook.type in ["transfer.failed", "transfer.reversed", "payment_intent.payment_failed"]:
            reimb.status = "APPROVED"
            log_audit_action(
                db=db,
                entity_id=reimb.entity_id,
                user_id=None,
                action="REIMBURSEMENT_PAYMENT_FAILED",
                details={"reimbursement_id": reimb.id, "transfer_ref": ref, "error": "Webhook failure event"}
            )
        db.commit()
        return {"status": "success", "mapped": "reimbursement"}

    return {"status": "ignored", "detail": "Reference not associated with any bill or reimbursement"}

def check_pending_transfers_internal(db: Session, entity_id: str):
    pass
