import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.entities_rbac.models import Role, Entity, User, Department, UserRole, OnboardingStatus
from app.cards.models import SpendProgram, Card, CardRequest
from app.transactions.models import Transaction
from app.ledger.models import LedgerEntry
from app.entities_rbac.auth import get_password_hash

from sqlalchemy import event

# In-memory SQLite for rapid unit testing of logic
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
app.database.SessionLocal = TestingSessionLocal
app.transactions.tasks.SessionLocal = TestingSessionLocal

@pytest.fixture(scope="module")
def db_session():
    import os
    for f in ["./test.db", "./test_ledger.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    # Setup test schemas / tables
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

def test_fintech_flow(client, db_session):
    # 1. Seed Roles
    for role_id in ["ADMIN", "MANAGER", "EMPLOYEE", "BOOKKEEPER", "AP_APPROVER"]:
        db_session.add(Role(id=role_id, name=role_id.title()))
    db_session.commit()

    # 2. Seed Entity
    entity = Entity(
        name="Apex Corporation",
        onboarding_status=OnboardingStatus.APPROVED.value
    )
    db_session.add(entity)
    db_session.flush()

    # 3. Seed Department
    dept = Department(name="Engineering", entity_id=entity.id)
    db_session.add(dept)
    db_session.flush()

    # 4. Seed Admin & Employee
    admin_user = User(
        name="Alice Admin",
        email="admin@apex.com",
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
    db_session.add(employee_user)
    db_session.flush()

    # 5. Assign Roles
    db_session.add(UserRole(user_id=admin_user.id, role_id="ADMIN", entity_id=entity.id))
    db_session.add(UserRole(user_id=employee_user.id, role_id="EMPLOYEE", entity_id=entity.id, department_id=dept.id))
    db_session.commit()

    # --- API Authentications ---
    # Login Admin
    response = client.post("/api/auth/token", data={"username": "admin@apex.com", "password": "password123"})
    assert response.status_code == 200
    admin_token = response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Entity-Id": entity.id}

    # Login Employee
    response = client.post("/api/auth/token", data={"username": "employee@apex.com", "password": "password123"})
    assert response.status_code == 200
    employee_token = response.json()["access_token"]
    employee_headers = {"Authorization": f"Bearer {employee_token}", "X-Entity-Id": entity.id}

    # Verify user me profile
    response = client.get("/api/auth/me", headers=employee_headers)
    assert response.status_code == 200
    assert response.json()["roles"] == ["EMPLOYEE"]

    # --- Spend Program & Card Issuance ---
    # Create spend program (Admin only)
    response = client.post("/api/cards/spend-programs", headers=admin_headers, json={
        "name": "SaaS Spend",
        "limit_amount": 5000.0,
        "limit_type": "MONTHLY"
    })
    assert response.status_code == 200
    program_id = response.json()["id"]

    # Request card (Employee)
    response = client.post("/api/cards/request", headers=employee_headers, json={
        "spend_program_id": program_id,
        "type": "VIRTUAL",
        "limit_amount": 1000.0
    })
    assert response.status_code == 200
    req_id = response.json()["id"]
    assert response.json()["status"] == "PENDING_APPROVAL"

    # Approve request (Admin)
    response = client.post(f"/api/cards/requests/{req_id}/approve", headers=admin_headers)
    assert response.status_code == 200
    card_id = response.json()["id"]
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["masked_pan"].startswith("****")

    # Freeze Card (Employee)
    response = client.post(f"/api/cards/{card_id}/freeze", headers=employee_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "FROZEN"

    # Unfreeze Card
    response = client.post(f"/api/cards/{card_id}/unfreeze", headers=employee_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"

    # --- Simulated Transactions & Ledger ---
    # Simulate card swipe exceeding limit
    response = client.post("/api/transactions/simulate-swipe", headers=employee_headers, json={
        "card_id": card_id,
        "amount": 1500.00,  # Card limit is 1000.0
        "merchant_name": "GitHub Inc",
        "merchant_mcc": "4816"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "DECLINED"
    assert response.json()["decline_reason"] == "Exceeds card limit"

    # Simulate card swipe within limit
    response = client.post("/api/transactions/simulate-swipe", headers=employee_headers, json={
        "card_id": card_id,
        "amount": 250.00,
        "merchant_name": "AWS Cloud Services",
        "merchant_mcc": "4816"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED (HELD)"
    tx_id = response.json()["transaction_id"]

    # Verify ledger entries created (double entry)
    holds = db_session.query(LedgerEntry).filter(LedgerEntry.transaction_id == tx_id).all()
    assert len(holds) == 2
    assert holds[0].amount == Decimal("250.00")
    
    # If not already settled (e.g. async queue), run settlement synchronously
    if holds[0].state == "HELD":
        from app.transactions.tasks import process_settlement as sync_process_settlement
        success = sync_process_settlement(tx_id, 250.00)
        assert success is True

    # Verify transaction is SETTLED and categorized
    tx = db_session.query(Transaction).filter(Transaction.id == tx_id).first()
    assert tx.status == "SETTLED"
    assert tx.category == "Software & SaaS"

    # Verify ledger entries transitioned to SETTLED
    settlements = db_session.query(LedgerEntry).filter(LedgerEntry.transaction_id == tx_id).all()
    for entry in settlements:
        assert entry.state == "SETTLED"

    # --- Reporting ---
    response = client.get("/api/reporting/dashboard", headers=employee_headers)
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["metrics"]["total_spend"] == 250.0
    assert metrics["metrics"]["active_cards"] == 1
    assert metrics["spend_by_department"][0]["amount"] == 250.0
    assert metrics["spend_by_category"][0]["category"] == "Software & SaaS"
