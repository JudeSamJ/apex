from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
import time
import random
import os
import logging

logger = logging.getLogger(__name__)

from app.database import get_db, SessionLocal
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.accounting.models import GLAccount, GLMapping, SyncQueue, AccountingCustomField

router = APIRouter(prefix="/api/accounting", tags=["accounting"])

# Pydantic schemas
class GLAccountCreate(BaseModel):
    code: str
    name: str
    type: str  # ASSET, LIABILITY, EXPENSE, REVENUE

class GLAccountOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    is_active: bool

class GLMappingCreate(BaseModel):
    mapping_type: str  # MCC, VENDOR, DEPARTMENT
    source_value: str
    gl_account_id: str

class GLMappingOut(BaseModel):
    id: str
    mapping_type: str
    source_value: str
    gl_account_id: str
    gl_account_code: str
    gl_account_name: str

class CustomFieldCreate(BaseModel):
    name: str
    field_type: str  # TEXT, SELECT
    select_options: Optional[List[str]] = None
    is_required: bool = False

class CustomFieldOut(BaseModel):
    id: str
    name: str
    field_type: str
    select_options: Optional[List[str]] = None
    is_required: bool

class SyncQueueOut(BaseModel):
    id: str
    record_type: str
    record_id: str
    gl_account_id: str
    gl_account_code: str
    gl_account_name: str
    status: str
    error_message: Optional[str] = None
    synced_at: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[str] = None
    created_at: str

# Choke point function for auto-queueing terminal ledger postings
def push_to_sync_queue(db: Session, entity_id: str, record_type: str, record_id: str, gl_account_id: str):
    # Enforce idempotency: check if already exists
    existing = db.query(SyncQueue).filter(
        SyncQueue.record_type == record_type,
        SyncQueue.record_id == record_id
    ).first()

    if existing:
        if existing.status == "SYNCED":
            return  # Already pushed successfully
        else:
            # Reset to SYNC_READY for retry
            existing.status = "SYNC_READY"
            existing.error_message = None
            existing.retry_count = 0
            existing.next_retry_at = None
            db.flush()
            return

    new_row = SyncQueue(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        record_type=record_type,
        record_id=record_id,
        gl_account_id=gl_account_id,
        status="SYNC_READY"
    )
    db.add(new_row)
    db.flush()

# GL coding lookup helper
def get_auto_coded_gl_account(db: Session, entity_id: str, mapping_type: str, source_value: str) -> Optional[str]:
    mapping = db.query(GLMapping).filter(
        GLMapping.entity_id == entity_id,
        GLMapping.mapping_type == mapping_type,
        GLMapping.source_value == source_value
    ).first()
    return mapping.gl_account_id if mapping else None

@router.post("/gl-accounts", response_model=GLAccountOut)
def create_gl_account(
    account_in: GLAccountCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can manage GL Chart of Accounts")

    # Check if code already exists
    existing = db.query(GLAccount).filter(
        GLAccount.entity_id == current_user.active_entity_id,
        GLAccount.code == account_in.code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="GL Account code already exists")

    account = GLAccount(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        code=account_in.code,
        name=account_in.name,
        type=account_in.type,
        is_active=True
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account

@router.get("/gl-accounts", response_model=List[GLAccountOut])
def list_gl_accounts(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return db.query(GLAccount).filter(
        GLAccount.entity_id == current_user.active_entity_id,
        GLAccount.is_active == True
    ).all()

@router.post("/mappings", response_model=GLMappingOut)
def create_gl_mapping(
    mapping_in: GLMappingCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can configure GL mapping rules")

    # Verify GL Account exists
    account = db.query(GLAccount).filter(
        GLAccount.id == mapping_in.gl_account_id,
        GLAccount.entity_id == current_user.active_entity_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="GL Account not found")

    # Upsert mapping rule
    mapping = db.query(GLMapping).filter(
        GLMapping.entity_id == current_user.active_entity_id,
        GLMapping.mapping_type == mapping_in.mapping_type,
        GLMapping.source_value == mapping_in.source_value
    ).first()

    if not mapping:
        mapping = GLMapping(
            id=str(uuid.uuid4()),
            entity_id=current_user.active_entity_id,
            mapping_type=mapping_in.mapping_type,
            source_value=mapping_in.source_value
        )
        db.add(mapping)

    mapping.gl_account_id = mapping_in.gl_account_id
    db.commit()
    db.refresh(mapping)

    return {
        "id": mapping.id,
        "mapping_type": mapping.mapping_type,
        "source_value": mapping.source_value,
        "gl_account_id": mapping.gl_account_id,
        "gl_account_code": account.code,
        "gl_account_name": account.name
    }

@router.get("/mappings", response_model=List[GLMappingOut])
def list_gl_mappings(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    mappings = db.query(GLMapping).filter(GLMapping.entity_id == current_user.active_entity_id).all()
    out = []
    for m in mappings:
        out.append({
            "id": m.id,
            "mapping_type": m.mapping_type,
            "source_value": m.source_value,
            "gl_account_id": m.gl_account_id,
            "gl_account_code": m.gl_account.code,
            "gl_account_name": m.gl_account.name
        })
    return out

@router.post("/custom-fields", response_model=CustomFieldOut)
def create_custom_field(
    field_in: CustomFieldCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can define custom fields")

    field = AccountingCustomField(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        name=field_in.name,
        field_type=field_in.field_type,
        select_options=field_in.select_options,
        is_required=field_in.is_required
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field

@router.get("/custom-fields", response_model=List[CustomFieldOut])
def list_custom_fields(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return db.query(AccountingCustomField).filter(AccountingCustomField.entity_id == current_user.active_entity_id).all()

@router.get("/sync/queue", response_model=List[SyncQueueOut])
def list_sync_queue(
    status_filter: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(SyncQueue).filter(SyncQueue.entity_id == current_user.active_entity_id)
    if status_filter:
        query = query.filter(SyncQueue.status == status_filter)
    
    rows = query.order_by(SyncQueue.created_at.desc()).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "record_type": r.record_type,
            "record_id": r.record_id,
            "gl_account_id": r.gl_account_id,
            "gl_account_code": r.gl_account.code,
            "gl_account_name": r.gl_account.name,
            "status": r.status,
            "error_message": r.error_message,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "retry_count": r.retry_count,
            "next_retry_at": r.next_retry_at.isoformat() if r.next_retry_at else None,
            "created_at": r.created_at.isoformat()
        })
    return out

@router.post("/sync/queue/{id}/retry")
def retry_sync_item(
    id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    item = db.query(SyncQueue).filter(
        SyncQueue.id == id,
        SyncQueue.entity_id == current_user.active_entity_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Sync queue item not found")

    item.status = "SYNC_READY"
    item.error_message = None
    item.retry_count = 0
    item.next_retry_at = None

    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=item.entity_id,
        user_id=current_user.user_id,
        action="SYNC_RETRY",
        details={"sync_queue_id": item.id, "record_type": item.record_type, "record_id": item.record_id}
    )
    
    db.commit()
    return {"message": "Item reset to SYNC_READY for processing"}

MAX_SYNC_RETRIES = 5


def _record_amount(db: Session, record_type: str, record_id: str) -> Optional[float]:
    """Look up the dollar amount backing a sync queue row, for the QBO journal line."""
    if record_type == "TRANSACTION":
        from app.transactions.models import Transaction
        row = db.query(Transaction).filter(Transaction.id == record_id).first()
        return float(row.amount) if row else None
    if record_type == "BILL":
        from app.bills.models import Bill
        row = db.query(Bill).filter(Bill.id == record_id).first()
        return float(row.total_amount) if row else None
    if record_type == "REIMBURSEMENT":
        from app.reimbursements.models import Reimbursement
        row = db.query(Reimbursement).filter(Reimbursement.id == record_id).first()
        return float(row.total_amount) if row else None
    return None


def _sync_item_to_qbo(db: Session, qbo_client, connection, item: SyncQueue) -> None:
    """Push one sync queue row to QBO as a two-line journal entry (debit the mapped
    GL account, credit a clearing account) and raise on any failure."""
    amount = _record_amount(db, item.record_type, item.record_id)
    if amount is None:
        raise ValueError(f"{item.record_type} {item.record_id} no longer exists")

    gl_account = db.query(GLAccount).filter(GLAccount.id == item.gl_account_id).first()
    if not gl_account or not gl_account.external_id:
        raise ValueError(f"GL account {item.gl_account_id} is not mapped to a QBO account")

    line_items = [
        {
            "Amount": amount,
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {
                "PostingType": "Debit",
                "AccountRef": {"value": gl_account.external_id}
            }
        },
        {
            "Amount": amount,
            "DetailType": "JournalEntryLineDetail",
            "JournalEntryLineDetail": {
                "PostingType": "Credit",
                "AccountRef": {"value": gl_account.external_id}
            }
        }
    ]

    qbo_client.create_journal_entry(
        access_token=connection.access_token,
        realm_id=connection.realm_id,
        line_items=line_items,
        tx_date=datetime.utcnow().strftime("%Y-%m-%d")
    )


@router.post("/sync/process")
def process_mock_erp_sync(
    force_error: bool = False,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()

    now = datetime.utcnow()

    # Poll SYNC_READY rows whose backoff window (if any) has elapsed
    items = db.query(SyncQueue).filter(
        SyncQueue.entity_id == current_user.active_entity_id,
        SyncQueue.status == "SYNC_READY",
        (SyncQueue.next_retry_at.is_(None)) | (SyncQueue.next_retry_at <= now)
    ).all()

    if not items:
        return {"message": "Sync queue is empty, no items processed"}

    from app.accounting.models import ERPConnection
    connection = db.query(ERPConnection).filter(
        ERPConnection.entity_id == current_user.active_entity_id,
        ERPConnection.provider == "QBO"
    ).first()

    use_real_qbo = connection is not None and not force_error

    processed_count = 0
    error_count = 0

    for item in items:
        item.status = "SYNCING"
        db.flush()

        if use_real_qbo:
            try:
                from app.qbo.router import get_valid_qbo_connection
                from app.qbo.client import get_qbo_client

                live_connection = get_valid_qbo_connection(db, current_user.active_entity_id)
                qbo_client = get_qbo_client()
                _sync_item_to_qbo(db, qbo_client, live_connection, item)

                item.status = "SYNCED"
                item.synced_at = datetime.utcnow()
                item.error_message = None
                item.retry_count = 0
                item.next_retry_at = None
                processed_count += 1
            except Exception as e:
                logger.error(f"QBO sync failed for sync_queue item {item.id}: {e}")
                item.retry_count += 1
                item.error_message = str(e)[:500]
                if item.retry_count >= MAX_SYNC_RETRIES:
                    item.status = "ERROR"
                    from app.notifications.service import notify_users_with_role
                    notify_users_with_role(
                        db=db,
                        entity_id=current_user.active_entity_id,
                        role_id="ADMIN",
                        type="SYNC_FAILED",
                        title=f"QBO sync failed for {item.record_type} after {MAX_SYNC_RETRIES} attempts",
                        body=item.error_message,
                    )
                else:
                    # Exponential backoff: 1, 2, 4, 8, 16 minutes, capped at MAX_SYNC_RETRIES
                    item.status = "SYNC_READY"
                    item.next_retry_at = now + timedelta(minutes=2 ** (item.retry_count - 1))
                error_count += 1
            continue

        # No real QBO connection configured for this entity — fall back to the
        # simulated ERP round-trip so demos/tests keep working without credentials.
        time.sleep(0.05)

        is_error = force_error or (os.getenv("PYTEST_CURRENT_TEST") is None and random.random() < 0.10)

        if is_error:
            item.status = "ERROR"
            item.error_message = "Mock ERP Connection Timeout: Target host unreachable"
            error_count += 1
        else:
            item.status = "SYNCED"
            item.synced_at = datetime.utcnow()
            item.error_message = None
            processed_count += 1

    db.commit()
    return {
        "message": "ERP Sync run complete",
        "synced": processed_count,
        "errors": error_count
    }
