import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from decimal import Decimal
import os

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.entities_rbac.models import Role, Entity, User, Department, UserRole, OnboardingStatus
from app.cards.models import SpendProgram, Card, CardRequest
from app.approvals.models import Approval, ApprovalStep, ApprovalRule
from app.bills.models import Vendor, VendorContact, VendorBankAccount, Bill, BillLineItem, BillPayment
from app.reimbursements.models import Reimbursement, ReimbursementLineItem, MileageTrip, TripWaypoint
from app.entities_rbac.auth import get_password_hash

# Create isolated test database file
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("ATTACH DATABASE './test_ledger.db' AS ledger;")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import app.database
import app.transactions.tasks
import app.bills.router
import app.reimbursements.router

@pytest.fixture(scope="module")
def db_session():
    for f in ["./test.db", "./test_ledger.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    # Redirect the session factory here (fixture setup), not at module import
    # time — pytest imports every test module during collection before
    # running any test, so a module-level assignment would let whichever
    # test file is collected last silently win this global for the entire
    # session, pointing every other module's DB-touching code at the wrong
    # engine.
    app.database.SessionLocal = TestingSessionLocal
    app.transactions.tasks.SessionLocal = TestingSessionLocal
    app.bills.router.SessionLocal = TestingSessionLocal
    app.reimbursements.router.SessionLocal = TestingSessionLocal

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

@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()

def test_phase2_fintech_flow(client, db_session):
    # 1. Seed Roles
    for role_id in ["ADMIN", "MANAGER", "EMPLOYEE", "BOOKKEEPER", "AP_APPROVER"]:
        db_session.add(Role(id=role_id, name=role_id))
    db_session.commit()

    # 2. Seed Entities
    entity = Entity(
        name="Apex Corp",
        onboarding_status=OnboardingStatus.APPROVED.value
    )
    db_session.add(entity)
    db_session.flush()

    # 3. Seed Department
    dept = Department(name="Engineering", entity_id=entity.id)
    db_session.add(dept)
    db_session.flush()

    # 4. Seed Users
    admin_user = User(
        name="Alice Admin",
        email="admin@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    manager_user = User(
        name="Bob Manager",
        email="manager@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    employee_user = User(
        name="Charlie Employee",
        email="employee@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db_session.add(admin_user)
    db_session.add(manager_user)
    db_session.add(employee_user)
    db_session.flush()

    # 5. Assign Roles
    db_session.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))
    db_session.add(UserRole(user_id=manager_user.id, role_id="MANAGER", entity_id=entity.id, department_id=dept.id))
    db_session.add(UserRole(user_id=employee_user.id, role_id="EMPLOYEE", entity_id=entity.id, department_id=dept.id))
    db_session.commit()

    # 6. Seed Custom ApprovalRules
    rule_card = ApprovalRule(
        entity_id=entity.id,
        applies_to="CARD_REQUEST",
        min_amount=Decimal("2000.00"),
        required_steps=["MANAGER", "ADMIN"]
    )
    rule_bill = ApprovalRule(
        entity_id=entity.id,
        applies_to="BILL",
        min_amount=Decimal("1000.00"),
        required_steps=["ADMIN"]
    )
    db_session.add(rule_card)
    db_session.add(rule_bill)
    db_session.commit()

    # --- API Authentications ---
    # Login Employee
    response = client.post("/api/auth/token", data={"username": "employee@apex.com", "password": "password123"})
    assert response.status_code == 200
    employee_headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # Login Manager
    response = client.post("/api/auth/token", data={"username": "manager@apex.com", "password": "password123"})
    assert response.status_code == 200
    manager_headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # Login Admin
    response = client.post("/api/auth/token", data={"username": "admin@apex.com", "password": "password123"})
    assert response.status_code == 200
    admin_headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # Seed Spend Program
    prog = SpendProgram(name="Core Stipend", limit_amount=5000.00, limit_type="MONTHLY", entity_id=entity.id)
    db_session.add(prog)
    db_session.commit()

    # ==========================================
    # WORKFLOW 1: Card Request & Approval Engine
    # ==========================================
    # Employee requests card with limit $2500 (exceeds $2000 rule threshold -> MANAGER & ADMIN steps)
    response = client.post("/api/cards/request", headers=employee_headers, json={
        "spend_program_id": prog.id,
        "type": "VIRTUAL",
        "limit_amount": 2500.00
    })
    assert response.status_code == 200
    req_id = response.json()["id"]

    # Verify Approval steps created (Step 1: MANAGER, Step 2: ADMIN)
    approval = db_session.query(Approval).filter(Approval.approvable_id == req_id).first()
    assert approval is not None
    assert approval.total_steps == 2
    assert approval.state == "SUBMITTED"

    # Step 1 Inbox Check for Manager (Bob)
    response = client.get("/api/approvals/inbox", headers=manager_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    step_id = response.json()[0]["id"]

    # Bob Manager approves Step 1
    response = client.post(f"/api/approvals/steps/{step_id}/decide", headers=manager_headers, json={
        "decision": "APPROVED",
        "comment": "Manager approved"
    })
    assert response.status_code == 200
    db_session.refresh(approval)
    assert approval.state == "IN_REVIEW"
    assert approval.current_step == 2

    # Step 2 Inbox Check for Admin (Alice)
    response = client.get("/api/approvals/inbox", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    step2_id = response.json()[0]["id"]

    # Alice Admin approves final Step 2
    response = client.post(f"/api/approvals/steps/{step2_id}/decide", headers=admin_headers, json={
        "decision": "APPROVED",
        "comment": "Admin final approval"
    })
    assert response.status_code == 200
    db_session.refresh(approval)
    assert approval.state == "APPROVED"

    # Verify CardRequest is APPROVED and Card was issued
    req = db_session.query(CardRequest).filter(CardRequest.id == req_id).first()
    assert req.status == "APPROVED"
    card = db_session.query(Card).filter(Card.owner_id == employee_user.id).first()
    assert card is not None
    assert card.status == "ACTIVE"

    # ==========================================
    # WORKFLOW 2: Bill Pay accounts payable (AP)
    # ==========================================
    # Create Vendor
    response = client.post("/api/bills/vendors", headers=employee_headers, json={
        "name": "AWS Billing Services LLC",
        "email": "billing@aws.amazon.com",
        "masked_bank_account": "ach_routing_token_999"
    })
    assert response.status_code == 200
    vendor_id = response.json()["id"]

    # Create Duplicate Vendor (Fuzzy Check triggers: matches name and returns existing vendor)
    response = client.post("/api/bills/vendors", headers=employee_headers, json={
        "name": "AWS Billing Services",
        "email": "billing@aws.amazon.com",
        "masked_bank_account": "ach_routing_token_999"
    })
    assert response.status_code == 200
    assert response.json()["id"] == vendor_id  # Reused vendor_id

    # Create Draft Bill for $1200 (payment BANK_TRANSFER)
    response = client.post("/api/bills", headers=employee_headers, json={
        "department_id": dept.id,
        "vendor_id": vendor_id,
        "due_date": "2026-08-01",
        "payment_method": "BANK_TRANSFER",
        "line_items": [
            {"description": "EC2 Instances", "amount": 800.00},
            {"description": "S3 Cloud Storage", "amount": 400.00}
        ]
    })
    assert response.status_code == 200
    bill_id = response.json()["id"]
    assert response.json()["status"] == "DRAFT"

    # Submit Bill for Approvals -> evaluated amount $1200 > $1000 rule threshold -> requires ADMIN review
    response = client.post(f"/api/bills/{bill_id}/submit", headers=employee_headers)
    assert response.status_code == 200
    
    bill = db_session.query(Bill).filter(Bill.id == bill_id).first()
    assert bill.status == "PENDING_APPROVAL"

    # Admin Inbox approves Bill Step
    response = client.get("/api/approvals/inbox", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    bill_step_id = response.json()[0]["id"]

    response = client.post(f"/api/approvals/steps/{bill_step_id}/decide", headers=admin_headers, json={
        "decision": "APPROVED"
    })
    assert response.status_code == 200
    db_session.refresh(bill)
    assert bill.status == "APPROVED"

    # Pay Bill (triggers PaymentRailClient bank transfer)
    response = client.post(f"/api/bills/{bill_id}/pay", headers=admin_headers)
    assert response.status_code == 200
    db_session.refresh(bill)
    assert bill.status == "PAID"
    assert len(bill.payments) == 1
    assert bill.payments[0].transfer_ref.startswith("ref_ach_")

    # ==========================================
    # WORKFLOW 3: Out-of-Pocket & Mileage Claims
    # ==========================================
    # Submit Mileage Claim for 120 miles -> computed payout $80.40 (120 * 0.67) -> routes to default MANAGER review
    response = client.post("/api/reimbursements", headers=employee_headers, json={
        "type": "MILEAGE",
        "department_id": dept.id,
        "trip": {
            "purpose": "Onsite system integration audit",
            "total_miles": 120.0,
            "waypoints": [
                {"sequence": 1, "address": "123 Office Headquarters"},
                {"sequence": 2, "address": "456 Client Enterprise Site"}
            ]
        }
    })
    assert response.status_code == 200
    reimb_id = response.json()["id"]
    assert float(response.json()["total_amount"]) == 80.40
    assert response.json()["status"] == "SUBMITTED"

    # Manager Inbox check and approval
    response = client.get("/api/approvals/inbox", headers=manager_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    reimb_step_id = response.json()[0]["id"]

    response = client.post(f"/api/approvals/steps/{reimb_step_id}/decide", headers=manager_headers, json={
        "decision": "APPROVED"
    })
    assert response.status_code == 200
    
    reimb = db_session.query(Reimbursement).filter(Reimbursement.id == reimb_id).first()
    assert reimb.status == "APPROVED"

    # Payout Reimbursement Claim
    response = client.post(f"/api/reimbursements/{reimb_id}/payout", headers=admin_headers)
    assert response.status_code == 200
    db_session.refresh(reimb)
    assert reimb.status == "REIMBURSED"
    assert response.json()["transfer_ref"].startswith("ref_ach_")
