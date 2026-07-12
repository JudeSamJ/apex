import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal
from sqlalchemy import event
import os
from datetime import datetime

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.entities_rbac.models import Role, Entity, User, Department, UserRole, OnboardingStatus
from app.cards.models import SpendProgram, Card, CardRequest
from app.transactions.models import Transaction
from app.ledger.models import LedgerEntry
from app.entities_rbac.auth import get_password_hash
from app.audit_logs.models import AuditLog
from app.jobs.models import BackgroundJob
from app.ledger.client import LedgerClient
from app.rate_limit import check_rate_limit, _request_history

# Setup in-memory sqlite connection for hardening test run
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("ATTACH DATABASE './test_ledger.db' AS ledger;")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redirect database references
import app.database
import app.transactions.tasks
app.database.SessionLocal = TestingSessionLocal
app.transactions.tasks.SessionLocal = TestingSessionLocal

client = TestClient(fastapi_app)

@pytest.fixture(scope="module", autouse=True)
def db_session():
    for f in ["./test.db", "./test_ledger.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        for f in ["./test.db", "./test_ledger.db"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

@pytest.fixture(autouse=True)
def clean_history():
    _request_history.clear()

def test_rate_limiting():
    for i in range(5):
        check_rate_limit(user_id="test_user", endpoint="test_endpoint", limit=5, window_seconds=10)
    
    with pytest.raises(Exception) as exc:
        check_rate_limit(user_id="test_user", endpoint="test_endpoint", limit=5, window_seconds=10)
    assert "Too many requests" in str(exc.value.detail)

def test_ledger_idempotency_postings(db_session):
    db = db_session
    ent = Entity(id="hardening-ent-1", name="Hardening Entity", onboarding_status="APPROVED")
    dept = Department(id="hardening-dept-1", entity_id=ent.id, name="Hardening Dept")
    db.add_all([ent, dept])
    db.commit()

    tx_id = "tx-hard-1"
    key = "idemp-key-hard-1"

    LedgerClient.post_hold(
        db=db,
        entity_id=ent.id,
        department_id=dept.id,
        card_id="card-hard-1",
        transaction_id=tx_id,
        amount=Decimal("150.00"),
        currency="USD",
        idempotency_key=key,
        source_event_id=tx_id
    )

    LedgerClient.post_hold(
        db=db,
        entity_id=ent.id,
        department_id=dept.id,
        card_id="card-hard-1",
        transaction_id=tx_id,
        amount=Decimal("150.00"),
        currency="USD",
        idempotency_key=key,
        source_event_id=tx_id
    )

    entries = db.query(LedgerEntry).filter(LedgerEntry.entity_id == ent.id).all()
    assert len(entries) == 2

def test_audit_logs_creation(db_session):
    db = db_session
    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id="hardening-ent-1",
        user_id=None,
        action="LIMIT_CHANGE",
        details={"card_id": "card-1", "new_limit": 5000.0}
    )
    db.commit()

    log = db.query(AuditLog).filter(AuditLog.entity_id == "hardening-ent-1").first()
    assert log is not None
    assert log.action == "LIMIT_CHANGE"
    assert log.details["new_limit"] == 5000.0

def test_background_job_error_state(db_session):
    db = db_session
    job_tx_id = "non-existent-tx-id"
    job = BackgroundJob(
        entity_id="hardening-ent-1",
        job_type="SETTLEMENT",
        source_event_id=job_tx_id,
        status="FAILED",
        error_message="Ledger hold not found"
    )
    db.add(job)
    db.commit()

    db_job = db.query(BackgroundJob).filter(BackgroundJob.source_event_id == job_tx_id).first()
    assert db_job.status == "FAILED"
    assert "Ledger hold" in db_job.error_message

def test_payment_rail_webhook_bill_flow(db_session):
    db = db_session
    from app.bills.models import Bill, BillPayment, Vendor
    
    vendor = Vendor(id="vend-hard-1", entity_id="hardening-ent-1", name="Stripe Vendor")
    bill = Bill(
        id="bill-hard-1",
        entity_id="hardening-ent-1",
        department_id="hardening-dept-1",
        vendor_id=vendor.id,
        status="APPROVED",
        due_date=datetime(2026, 12, 31),
        total_amount=Decimal("250.00"),
        payment_method="BANK_TRANSFER"
    )
    payment = BillPayment(
        id="pmt-hard-1",
        entity_id="hardening-ent-1",
        bill_id=bill.id,
        transfer_ref="pi_stripe_test_123"
    )
    db.add_all([vendor, bill, payment])
    db.commit()

    # 1. Simulate Completed Webhook
    response = client.post(
        "/api/bills/webhooks/payment-rail",
        json={"type": "transfer.completed", "transfer_ref": "pi_stripe_test_123"}
    )
    assert response.status_code == 200
    db.refresh(bill)
    assert bill.status == "PAID"

    # 2. Simulate Failed Webhook (moves status back to APPROVED)
    response = client.post(
        "/api/bills/webhooks/payment-rail",
        json={"type": "transfer.failed", "transfer_ref": "pi_stripe_test_123"}
    )
    assert response.status_code == 200
    db.refresh(bill)
    assert bill.status == "APPROVED"

