import os
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.entities_rbac.models import Role, Entity, Department, User, UserRole
from app.entities_rbac.auth import get_password_hash
from app.accounting.models import GLAccount, GLMapping, SyncQueue
from app.insights.models import Insight, MerchantNormalization
from app.reporting.models import Budget
from app.transactions.models import Transaction
from app.cards.models import SpendProgram, Card, CardRequest
from app.bills.models import Vendor, Bill, BillLineItem
from app.reimbursements.models import Reimbursement, ReimbursementLineItem
from app.approvals.models import Approval, ApprovalStep, ApprovalRule
from app.main import app as fastapi_app

# Create isolated test database file
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("ATTACH DATABASE './test_ledger.db' AS ledger;")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the session factory globally for test database redirection
import app.database
import app.transactions.tasks
import app.approvals.router
import app.bills.router
import app.reimbursements.router
import app.accounting.router
import app.insights.router
import app.reporting.router

app.database.SessionLocal = TestingSessionLocal
app.transactions.tasks.SessionLocal = TestingSessionLocal
app.approvals.router.SessionLocal = TestingSessionLocal
app.bills.router.SessionLocal = TestingSessionLocal
app.reimbursements.router.SessionLocal = TestingSessionLocal
app.accounting.router.SessionLocal = TestingSessionLocal
app.insights.router.SessionLocal = TestingSessionLocal
app.reporting.router.SessionLocal = TestingSessionLocal

@pytest.fixture(scope="module")
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

@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    fastapi_app.dependency_overrides[app.database.get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()

def test_phase3_full_flow(client, db_session):
    # 1. Seed Roles
    for role_id in ["ADMIN", "MANAGER", "EMPLOYEE", "BOOKKEEPER"]:
        db_session.add(Role(id=role_id, name=role_id.title()))
    db_session.commit()

    # 2. Seed Entity
    entity = Entity(
        name="Apex parent entity",
        onboarding_status="APPROVED"
    )
    db_session.add(entity)
    db_session.flush()

    # 3. Seed Department
    dept = Department(name="Engineering", entity_id=entity.id)
    db_session.add(dept)
    db_session.flush()

    # 4. Seed Admin, Bookkeeper & Employee
    admin_user = User(
        name="Alice Admin",
        email="admin3@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    employee_user = User(
        name="Charlie Employee",
        email="employee3@apex.com",
        entity_id=entity.id,
        password_hash=get_password_hash("password123")
    )
    db_session.add(admin_user)
    db_session.add(employee_user)
    db_session.flush()

    db_session.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))
    db_session.add(UserRole(user_id=employee_user.id, role_id="EMPLOYEE", entity_id=entity.id, department_id=dept.id))
    db_session.commit()

    # Get admin authorization header
    response = client.post("/api/auth/token", data={"username": "admin3@apex.com", "password": "password123"})
    assert response.status_code == 200
    admin_headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # Get employee authorization header
    response = client.post("/api/auth/token", data={"username": "employee3@apex.com", "password": "password123"})
    assert response.status_code == 200
    employee_headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Entity-Id": entity.id}

    # 5. Create GL Accounts
    response = client.post("/api/accounting/gl-accounts", headers=admin_headers, json={
        "code": "6100",
        "name": "Software Subscriptions",
        "type": "EXPENSE"
    })
    assert response.status_code == 200
    saas_gl_id = response.json()["id"]

    response = client.post("/api/accounting/gl-accounts", headers=admin_headers, json={
        "code": "6200",
        "name": "Vendor Services",
        "type": "EXPENSE"
    })
    assert response.status_code == 200
    vendor_gl_id = response.json()["id"]

    # 6. Configure Mappings
    # MCC 4816 maps to 6100
    response = client.post("/api/accounting/mappings", headers=admin_headers, json={
        "mapping_type": "MCC",
        "source_value": "4816",
        "gl_account_id": saas_gl_id
    })
    assert response.status_code == 200

    # 7. Seed budget
    response = client.post("/api/reporting/budgets", headers=admin_headers, json={
        "department_id": dept.id,
        "category": "Software & SaaS",
        "period": "2026-07",
        "amount": 1000.0
    })
    assert response.status_code == 200

    # 8. Settle card transaction (MCC 4816) -> verify auto-coding & sync queue row
    # Seed program & card
    program = SpendProgram(name="SaaS Spend", limit_amount=Decimal("5000.0"), limit_type="MONTHLY", entity_id=entity.id)
    db_session.add(program)
    db_session.flush()

    card = Card(
        entity_id=entity.id,
        owner_id=employee_user.id,
        department_id=dept.id,
        spend_program_id=program.id,
        type="VIRTUAL",
        limit_amount=Decimal("1000.0"),
        status="ACTIVE",
        masked_pan="************1234",
        card_token="tok_123"
    )
    db_session.add(card)
    db_session.flush()

    # Simulate Swipe (MCC 4816)
    response = client.post("/api/transactions/simulate-swipe", headers=employee_headers, json={
        "card_id": card.id,
        "amount": 150.0,
        "merchant_name": "AWS Services #1",
        "merchant_mcc": "4816"
    })
    tx_id = response.json()["transaction_id"]

    # Settle transaction using eager processing in celery
    from app.transactions.tasks import process_settlement
    process_settlement(tx_id, 150.0)

    # Verify transaction got GL account assigned
    tx_db = db_session.query(Transaction).filter(Transaction.id == tx_id).first()
    assert tx_db.gl_account_id == saas_gl_id
    assert tx_db.category == "Software & SaaS"

    # Verify item queued to ERP Sync
    response = client.get("/api/accounting/sync/queue", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["record_type"] == "TRANSACTION"
    assert response.json()[0]["status"] == "SYNC_READY"
    queue_id = response.json()[0]["id"]

    # 9. Test ERP Sync run & idempotency
    response = client.post("/api/accounting/sync/process", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["synced"] == 1
    assert response.json()["errors"] == 0

    # Idempotency checks
    response = client.get("/api/accounting/sync/queue", headers=admin_headers)
    assert response.json()[0]["status"] == "SYNCED"

    # 10. Force Error test & Manual recovery retry
    response = client.post(f"/api/accounting/sync/queue/{queue_id}/retry", headers=admin_headers)
    assert response.status_code == 200
    
    # Verify status returned to SYNC_READY
    response = client.get("/api/accounting/sync/queue", headers=admin_headers)
    assert response.json()[0]["status"] == "SYNC_READY"

    # Run with force_error
    response = client.post("/api/accounting/sync/process?force_error=true", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["errors"] == 1

    # Verify status is ERROR
    response = client.get("/api/accounting/sync/queue", headers=admin_headers)
    assert response.json()[0]["status"] == "ERROR"
    assert "Mock ERP" in response.json()[0]["error_message"]

    # Retry to restore consistency
    client.post(f"/api/accounting/sync/queue/{queue_id}/retry", headers=admin_headers)

    # 11. Anomaly Insights: seed 2 transactions of same amount to trigger duplicates
    # Let's seed AWS swipe 2
    response = client.post("/api/transactions/simulate-swipe", headers=employee_headers, json={
        "card_id": card.id,
        "amount": 150.0,
        "merchant_name": "AWS Services #2",
        "merchant_mcc": "4816"
    })
    tx_id2 = response.json()["transaction_id"]
    process_settlement(tx_id2, 150.0)

    # Run anomaly check
    response = client.post("/api/insights/detect", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["insights_created"] >= 1

    # Fetch insights feed
    response = client.get("/api/insights", headers=admin_headers)
    assert len(response.json()) >= 1
    insight_id = response.json()[0]["id"]
    assert response.json()[0]["status"] == "OPEN"
    assert response.json()[0]["type"] == "DUPLICATE_SUBSCRIPTION"

    # Confirm insight & verify savings rollup
    response = client.post(f"/api/insights/{insight_id}/confirm", headers=admin_headers)
    assert response.status_code == 200

    response = client.get("/api/insights/savings-summary", headers=admin_headers)
    assert response.json()["total_savings"] == 150.0

    # 12. Budgets Comparison
    response = client.get("/api/reporting/budgets", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert float(response.json()[0]["budgeted_amount"]) == 1000.0
    assert float(response.json()[0]["actual_amount"]) == 300.0  # Two transactions of 150.0
    assert float(response.json()[0]["remaining_amount"]) == 700.0

    # 13. Admin KPIs dashboard check
    response = client.get("/api/reporting/admin-kpis", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["operational_efficiency"] == 100.0
    assert response.json()["money_saved"] == 150.0
    assert response.json()["compliance_score"] == 100.0
