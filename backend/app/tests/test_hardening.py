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

def test_dwolla_webhook_rejects_invalid_signature(monkeypatch):
    import json
    import hmac
    import hashlib
    import app.webhooks.router as webhooks_router

    monkeypatch.setattr(webhooks_router, "DWOLLA_WEBHOOK_SECRET", "test_dwolla_secret")

    payload = json.dumps({
        "topic": "transfer_cancelled",
        "id": "evt-sig-test",
        "_links": {"resource": {"href": "https://api-sandbox.dwolla.com/transfers/unknown"}}
    }).encode()

    # Wrong/missing signature is rejected once a secret is configured
    response = client.post(
        "/api/webhooks/dwolla",
        content=payload,
        headers={"X-Request-Signature-SHA256": "not-the-real-signature"}
    )
    assert response.status_code == 400

    # Correctly signed payload is accepted
    valid_signature = hmac.new(b"test_dwolla_secret", payload, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/webhooks/dwolla",
        content=payload,
        headers={"X-Request-Signature-SHA256": valid_signature}
    )
    assert response.status_code == 200

def test_didit_webhook_rejects_invalid_signature(monkeypatch):
    import json
    import hmac
    import hashlib
    import app.webhooks.router as webhooks_router

    monkeypatch.setattr(webhooks_router, "DIDIT_WEBHOOK_SECRET", "test_didit_secret")

    payload = json.dumps({
        "verification_id": "verif-sig-test",
        "status": "pending",
        "external_id": "unknown-entity"
    }).encode()

    response = client.post(
        "/api/webhooks/didit",
        content=payload,
        headers={"X-Didit-Signature": "not-the-real-signature"}
    )
    assert response.status_code == 400

    valid_signature = hmac.new(b"test_didit_secret", payload, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/webhooks/didit",
        content=payload,
        headers={"X-Didit-Signature": valid_signature}
    )
    assert response.status_code == 200

def test_bill_pay_idempotency_key_prevents_double_payment(db_session):
    db = db_session
    from app.bills.models import Bill, BillPayment, Vendor

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="idem-ent-1", name="Idempotency Entity", onboarding_status="APPROVED")
    dept = Department(id="idem-dept-1", entity_id=entity.id, name="Idempotency Dept")
    admin_user = User(
        id="idem-admin-1",
        name="Idem Admin",
        email="idem-admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, dept, admin_user])
    db.flush()
    db.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))

    vendor = Vendor(id="idem-vend-1", entity_id=entity.id, name="Idempotency Vendor")
    bill = Bill(
        id="idem-bill-1",
        entity_id=entity.id,
        department_id=dept.id,
        vendor_id=vendor.id,
        status="APPROVED",
        due_date=datetime(2026, 12, 31),
        total_amount=Decimal("500.00"),
        payment_method="BANK_TRANSFER"
    )
    db.add_all([vendor, bill])
    db.commit()

    response = client.post(
        "/api/auth/token",
        data={"username": "idem-admin@apex.com", "password": "password123"}
    )
    assert response.status_code == 200
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Entity-Id": entity.id,
        "Idempotency-Key": "pay-idem-bill-1-attempt"
    }

    first = client.post(f"/api/bills/{bill.id}/pay", headers=headers)
    assert first.status_code == 200
    first_payment_id = first.json()["payment_id"]

    # A retry with the same Idempotency-Key must replay the original response,
    # not initiate a second transfer, even though the bill is no longer APPROVED.
    second = client.post(f"/api/bills/{bill.id}/pay", headers=headers)
    assert second.status_code == 200
    assert second.json()["payment_id"] == first_payment_id

    payments = db.query(BillPayment).filter(BillPayment.bill_id == bill.id).all()
    assert len(payments) == 1

    # A different Idempotency-Key against an already-PAID bill correctly 404s
    # instead of being treated as a replay.
    third = client.post(
        f"/api/bills/{bill.id}/pay",
        headers={**headers, "Idempotency-Key": "pay-idem-bill-1-different-attempt"}
    )
    assert third.status_code == 404

def test_vendor_sanctions_screening_flags_hit_and_blocks_payment(db_session):
    db = db_session
    from app.bills.models import Bill, Vendor

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="screen-ent-1", name="Screening Entity", onboarding_status="APPROVED")
    dept = Department(id="screen-dept-1", entity_id=entity.id, name="Screening Dept")
    admin_user = User(
        id="screen-admin-1",
        name="Screen Admin",
        email="screen-admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, dept, admin_user])
    db.flush()
    db.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))
    db.commit()

    response = client.post(
        "/api/auth/token",
        data={"username": "screen-admin@apex.com", "password": "password123"}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # A clean vendor name screens CLEAR and stays payable.
    clean = client.post(
        "/api/bills/vendors",
        headers=headers,
        json={"name": "Acme Supplies", "email": "ap@acme.example", "masked_bank_account": "acct_1234"}
    )
    assert clean.status_code == 200
    clean_vendor = db.query(Vendor).filter(Vendor.id == clean.json()["id"]).first()
    assert clean_vendor.screening_status == "CLEAR"

    # A vendor name matching the (mock) watchlist screens HIT.
    flagged = client.post(
        "/api/bills/vendors",
        headers=headers,
        json={"name": "OFAC TEST Holdings", "email": "ap@flagged.example", "masked_bank_account": "acct_5678"}
    )
    assert flagged.status_code == 200
    flagged_vendor_id = flagged.json()["id"]
    flagged_vendor = db.query(Vendor).filter(Vendor.id == flagged_vendor_id).first()
    assert flagged_vendor.screening_status == "HIT"

    from app.screening.models import SanctionsScreening
    screening_row = db.query(SanctionsScreening).filter(
        SanctionsScreening.subject_type == "VENDOR", SanctionsScreening.subject_id == flagged_vendor_id
    ).first()
    assert screening_row is not None
    assert screening_row.status == "HIT"

    # A bill against the flagged vendor cannot be paid, even once approved.
    bill = Bill(
        id="screen-bill-1",
        entity_id=entity.id,
        department_id=dept.id,
        vendor_id=flagged_vendor_id,
        status="APPROVED",
        due_date=datetime(2026, 12, 31),
        total_amount=Decimal("100.00"),
        payment_method="BANK_TRANSFER"
    )
    db.add(bill)
    db.commit()

    pay_response = client.post(f"/api/bills/{bill.id}/pay", headers=headers)
    assert pay_response.status_code == 403
    assert "sanctions screening" in pay_response.json()["detail"]

def test_stripe_dispute_webhook_creates_and_resolves_dispute(monkeypatch, db_session):
    db = db_session
    from app.cards.models import Card
    from app.disputes.models import CardDispute
    import app.webhooks.router as webhooks_router

    entity = db.query(Entity).filter(Entity.id == "hardening-ent-1").first()
    if not entity:
        entity = Entity(id="hardening-ent-1", name="Hardening Entity", onboarding_status="APPROVED")
        db.add(entity)
        db.commit()

    card = Card(
        id="disp-card-1",
        entity_id="hardening-ent-1",
        owner_id="disp-owner-1",
        department_id="hardening-dept-1",
        spend_program_id="disp-sp-1",
        type="VIRTUAL",
        limit_amount=Decimal("1000.00"),
        status="ACTIVE",
        masked_pan="**** **** **** 1234",
        card_token="ch_stripe_card_test_1"
    )
    db.add(card)
    db.commit()

    monkeypatch.setattr(
        webhooks_router,
        "_resolve_card_token_for_issuing_transaction",
        lambda ref: "ch_stripe_card_test_1"
    )

    response = client.post(
        "/api/webhooks/stripe",
        json={
            "type": "issuing_dispute.created",
            "data": {"object": {
                "id": "idp_test_1",
                "amount": 5000,
                "reason": "fraudulent",
                "status": "unsubmitted",
                "transaction": "ipi_test_txn_1"
            }}
        }
    )
    assert response.status_code == 200

    dispute = db.query(CardDispute).filter(CardDispute.stripe_dispute_id == "idp_test_1").first()
    assert dispute is not None
    assert dispute.status == "WARNING_NEEDS_RESPONSE"
    assert dispute.entity_id == "hardening-ent-1"
    assert dispute.card_id == "disp-card-1"
    assert float(dispute.amount) == 50.0

    response = client.post(
        "/api/webhooks/stripe",
        json={
            "type": "issuing_dispute.funds_reinstated",
            "data": {"object": {
                "id": "idp_test_1",
                "amount": 5000,
                "reason": "fraudulent",
                "status": "won",
                "transaction": "ipi_test_txn_1"
            }}
        }
    )
    assert response.status_code == 200
    db.refresh(dispute)
    assert dispute.status == "WON"

def test_reconciliation_flags_drift_between_local_and_provider_status(db_session):
    db = db_session
    from app.bills.models import Bill, BillPayment, Vendor
    from app.reimbursements.models import Reimbursement
    from app.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="recon-ent-1", name="Reconciliation Entity", onboarding_status="APPROVED")
    dept = Department(id="recon-dept-1", entity_id=entity.id, name="Recon Dept")
    admin_user = User(
        id="recon-admin-1",
        name="Recon Admin",
        email="recon-admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, dept, admin_user])
    db.flush()
    db.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))

    vendor = Vendor(id="recon-vend-1", entity_id=entity.id, name="Recon Vendor")
    # A bill we believe is PAID, but whose transfer_ref the mock payment rail
    # reports as "failed" — this must surface as a discrepancy.
    drifted_bill = Bill(
        id="recon-bill-drift",
        entity_id=entity.id,
        department_id=dept.id,
        vendor_id=vendor.id,
        status="PAID",
        due_date=datetime(2026, 12, 31),
        total_amount=Decimal("300.00"),
        payment_method="BANK_TRANSFER"
    )
    drifted_payment = BillPayment(
        id="recon-pmt-drift",
        entity_id=entity.id,
        bill_id=drifted_bill.id,
        transfer_ref="ref_ach_FAIL_TEST_1"
    )
    # A bill that's correctly PAID and matches the rail — must NOT be flagged.
    clean_bill = Bill(
        id="recon-bill-clean",
        entity_id=entity.id,
        department_id=dept.id,
        vendor_id=vendor.id,
        status="PAID",
        due_date=datetime(2026, 12, 31),
        total_amount=Decimal("150.00"),
        payment_method="BANK_TRANSFER"
    )
    clean_payment = BillPayment(
        id="recon-pmt-clean",
        entity_id=entity.id,
        bill_id=clean_bill.id,
        transfer_ref="ref_ach_ok_1"
    )
    drifted_reimbursement = Reimbursement(
        id="recon-reimb-drift",
        entity_id=entity.id,
        user_id=admin_user.id,
        department_id=dept.id,
        type="OUT_OF_POCKET",
        status="REIMBURSED",
        total_amount=Decimal("80.00"),
        transfer_ref="ref_ach_CANCEL_TEST_1"
    )
    db.add_all([vendor, drifted_bill, drifted_payment, clean_bill, clean_payment, drifted_reimbursement])
    db.commit()

    response = client.post(
        "/api/auth/token",
        data={"username": "recon-admin@apex.com", "password": "password123"}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    run_response = client.post("/api/reconciliation/run", headers=headers)
    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["status"] == "COMPLETED"
    assert run_body["checked_count"] == 3
    assert run_body["discrepancy_count"] == 2

    discrepancies_response = client.get(
        f"/api/reconciliation/runs/{run_body['id']}/discrepancies", headers=headers
    )
    assert discrepancies_response.status_code == 200
    discrepancies = discrepancies_response.json()
    assert len(discrepancies) == 2
    subject_ids = {d["subject_id"] for d in discrepancies}
    assert subject_ids == {"recon-pmt-drift", "recon-reimb-drift"}

    runs_response = client.get("/api/reconciliation/runs", headers=headers)
    assert runs_response.status_code == 200
    assert len(runs_response.json()) == 1

def test_mfa_enroll_confirm_and_two_step_login(db_session):
    db = db_session
    import pyotp

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="mfa-ent-1", name="MFA Entity", onboarding_status="APPROVED")
    user = User(
        id="mfa-user-1",
        name="MFA User",
        email="mfa-user@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, user])
    db.flush()
    db.add(UserRole(user_id=user.id, role_id="ADMIN", entity_id=entity.id))
    db.commit()

    # Plain login works before MFA is enabled: a real access_token comes back directly.
    login = client.post("/api/auth/token", data={"username": "mfa-user@apex.com", "password": "password123"})
    assert login.status_code == 200
    login_body = login.json()
    assert login_body["access_token"]
    assert login_body["mfa_required"] is False
    headers = {"Authorization": f"Bearer {login_body['access_token']}", "X-Entity-Id": entity.id}

    # A raw MFA challenge token must never work as a real access token.
    enroll = client.post("/api/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    assert enroll.json()["otpauth_url"].startswith("otpauth://")

    bad_confirm = client.post("/api/auth/mfa/confirm", headers=headers, json={"code": "000000"})
    assert bad_confirm.status_code == 400

    valid_code = pyotp.TOTP(secret).now()
    confirm = client.post("/api/auth/mfa/confirm", headers=headers, json={"code": valid_code})
    assert confirm.status_code == 200
    assert confirm.json()["mfa_enabled"] is True

    # Logging in again now yields a challenge, not a real token.
    login2 = client.post("/api/auth/token", data={"username": "mfa-user@apex.com", "password": "password123"})
    assert login2.status_code == 200
    login2_body = login2.json()
    assert login2_body["mfa_required"] is True
    assert login2_body["access_token"] is None
    challenge_token = login2_body["mfa_challenge_token"]

    # The challenge token alone must not authenticate a normal request.
    challenge_as_bearer = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {challenge_token}", "X-Entity-Id": entity.id}
    )
    assert challenge_as_bearer.status_code == 401

    # Wrong code at the verify step is rejected.
    bad_verify = client.post("/api/auth/mfa/verify-login", json={"challenge_token": challenge_token, "code": "000000"})
    assert bad_verify.status_code == 401

    # Correct code exchanges the challenge for a real access token.
    valid_code_2 = pyotp.TOTP(secret).now()
    good_verify = client.post(
        "/api/auth/mfa/verify-login", json={"challenge_token": challenge_token, "code": valid_code_2}
    )
    assert good_verify.status_code == 200
    real_token = good_verify.json()["access_token"]
    assert real_token

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {real_token}", "X-Entity-Id": entity.id})
    assert me.status_code == 200

    # Disabling MFA requires a valid code too.
    new_headers = {"Authorization": f"Bearer {real_token}", "X-Entity-Id": entity.id}
    bad_disable = client.post("/api/auth/mfa/disable", headers=new_headers, json={"code": "000000"})
    assert bad_disable.status_code == 400

    valid_code_3 = pyotp.TOTP(secret).now()
    disable = client.post("/api/auth/mfa/disable", headers=new_headers, json={"code": valid_code_3})
    assert disable.status_code == 200
    assert disable.json()["mfa_enabled"] is False

def test_notifications_created_and_readable(db_session):
    db = db_session
    from app.bills.models import Vendor
    from app.notifications.models import Notification

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="notif-ent-1", name="Notification Entity", onboarding_status="APPROVED")
    dept = Department(id="notif-dept-1", entity_id=entity.id, name="Notif Dept")
    admin_user = User(
        id="notif-admin-1",
        name="Notif Admin",
        email="notif-admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, dept, admin_user])
    db.flush()
    db.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))
    db.commit()

    response = client.post(
        "/api/auth/token",
        data={"username": "notif-admin@apex.com", "password": "password123"}
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # Creating a sanctions-flagged vendor must notify the entity's admins.
    flagged = client.post(
        "/api/bills/vendors",
        headers=headers,
        json={"name": "OFAC TEST Holdings", "email": "ap@flagged.example", "masked_bank_account": "acct_9999"}
    )
    assert flagged.status_code == 200

    notif_row = db.query(Notification).filter(
        Notification.entity_id == entity.id, Notification.type == "SANCTIONS_HIT"
    ).first()
    assert notif_row is not None
    assert notif_row.user_id == admin_user.id
    assert notif_row.email_sent is True

    list_response = client.get("/api/notifications", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()
    assert any(n["type"] == "SANCTIONS_HIT" and not n["read"] for n in items)

    notif_id = next(n["id"] for n in items if n["type"] == "SANCTIONS_HIT")
    read_response = client.post(f"/api/notifications/{notif_id}/read", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["read"] is True

    unread_response = client.get("/api/notifications?unread_only=true", headers=headers)
    assert all(n["id"] != notif_id for n in unread_response.json())

def test_transaction_csv_export(db_session):
    db = db_session
    import csv
    import io
    from app.cards.models import Card

    role = db.query(Role).filter(Role.id == "ADMIN").first()
    if not role:
        db.add(Role(id="ADMIN", name="Admin"))
        db.commit()

    entity = Entity(id="csv-ent-1", name="CSV Entity", onboarding_status="APPROVED")
    dept = Department(id="csv-dept-1", entity_id=entity.id, name="CSV Dept")
    admin_user = User(
        id="csv-admin-1",
        name="CSV Admin",
        email="csv-admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db.add_all([entity, dept, admin_user])
    db.flush()
    db.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))

    card = Card(
        id="csv-card-1",
        entity_id=entity.id,
        owner_id=admin_user.id,
        department_id=dept.id,
        spend_program_id="csv-sp-1",
        type="VIRTUAL",
        limit_amount=Decimal("1000.00"),
        status="ACTIVE",
        masked_pan="**** **** **** 4321",
        card_token="tok_csv_test"
    )
    tx = Transaction(
        id="csv-tx-1",
        entity_id=entity.id,
        department_id=dept.id,
        card_id=card.id,
        amount=Decimal("42.50"),
        currency="USD",
        merchant_name="CSV Export Test Merchant",
        merchant_mcc="5734",
        status="SETTLED"
    )
    db.add_all([card, tx])
    db.commit()

    response = client.post("/api/auth/token", data={"username": "csv-admin@apex.com", "password": "password123"})
    headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    export_response = client.get("/api/transactions/export.csv", headers=headers)
    assert export_response.status_code == 200
    assert "text/csv" in export_response.headers["content-type"]

    rows = list(csv.reader(io.StringIO(export_response.text)))
    assert rows[0] == [
        "id", "date", "owner", "card", "merchant", "mcc", "category",
        "amount", "currency", "status", "decline_reason"
    ]
    data_row = next(r for r in rows[1:] if r[0] == "csv-tx-1")
    assert data_row[4] == "CSV Export Test Merchant"
    assert Decimal(data_row[7]) == Decimal("42.50")
    assert data_row[9] == "SETTLED"

