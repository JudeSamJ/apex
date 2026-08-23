"""Section 1 foundation verification tests."""

import pytest
from decimal import Decimal
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.ledger.client import LedgerClient
from app.ledger.models import LedgerEntry, LedgerState, BalanceSnapshot
from app.ledger.transitions import validate_transition, TRANSITION_TABLE
from app.transactions.pipeline_events import emit_pipeline_event, PIPELINE_EVENT_TYPES
from app.transactions.models import PipelineEvent, Transaction
from app.entities_rbac.models import Entity, Department, User, OnboardingStatus
from app.cards.models import SpendProgram, Card
from app.entities_rbac.auth import get_password_hash
# Transaction.gl_account_id has a string FK to gl_accounts.id, so that table
# must be registered on Base.metadata before create_all() — importing the
# owning model is what registers it. Without this, running this file in
# isolation (not after another test module happens to import it first) fails
# with NoReferencedTableError.
from app.accounting.models import GLAccount

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_section1.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("ATTACH DATABASE './test_section1_ledger.db' AS ledger;")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    import os
    # Dispose the pool first: this fixture runs once per test (function
    # scope), and a pooled connection left open from the previous test can
    # still be attached to the just-deleted file's inode, which makes SQLite
    # report the freshly recreated file as "readonly" on the next test.
    engine.dispose()
    for f in ["./test_section1.db", "./test_section1_ledger.db"]:
        if os.path.exists(f):
            os.remove(f)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    for f in ["./test_section1.db", "./test_section1_ledger.db"]:
        if os.path.exists(f):
            os.remove(f)


def test_ledger_transition_table_enforces_valid_paths():
    validate_transition(LedgerState.PENDING_AUTH.value, LedgerState.HELD.value)
    validate_transition(LedgerState.HELD.value, LedgerState.SETTLED.value)
    validate_transition(LedgerState.HELD.value, LedgerState.REVERSED.value)

    with pytest.raises(ValueError, match="Invalid ledger state transition"):
        validate_transition(LedgerState.PENDING_AUTH.value, LedgerState.SETTLED.value)

    with pytest.raises(ValueError, match="Invalid ledger state transition"):
        validate_transition(LedgerState.DECLINED.value, LedgerState.HELD.value)

    assert LedgerState.SETTLED.value in TRANSITION_TABLE[LedgerState.HELD.value]


def test_post_hold_uses_pending_auth_then_held(db):
    entity = Entity(name="Test Co", onboarding_status=OnboardingStatus.APPROVED.value)
    db.add(entity)
    db.flush()
    dept = Department(name="Eng", entity_id=entity.id)
    db.add(dept)
    db.commit()

    tx_id = "tx-001"
    entries = LedgerClient.post_hold(
        db=db,
        entity_id=entity.id,
        department_id=dept.id,
        card_id=None,
        transaction_id=tx_id,
        amount=Decimal("100.00"),
        currency="USD",
        idempotency_key="hold_tx-001",
        source_event_id=tx_id,
    )
    assert len(entries) == 2
    assert all(e.state == LedgerState.HELD.value for e in entries)

    balance = LedgerClient.get_balances(db, entity.id)
    assert balance == Decimal("100.00")


def test_ledger_idempotency_and_settlement(db):
    entity = Entity(name="Test Co", onboarding_status=OnboardingStatus.APPROVED.value)
    db.add(entity)
    db.flush()
    dept = Department(name="Eng", entity_id=entity.id)
    db.add(dept)
    db.commit()

    tx_id = "tx-002"
    LedgerClient.post_hold(
        db=db,
        entity_id=entity.id,
        department_id=dept.id,
        card_id=None,
        transaction_id=tx_id,
        amount=Decimal("50.00"),
        currency="USD",
        idempotency_key="hold_tx-002",
        source_event_id=tx_id,
    )

    first = LedgerClient.post_settlement(
        db=db,
        transaction_id=tx_id,
        amount=Decimal("50.00"),
        idempotency_key="settle_tx-002",
        source_event_id=tx_id,
    )
    second = LedgerClient.post_settlement(
        db=db,
        transaction_id=tx_id,
        amount=Decimal("50.00"),
        idempotency_key="settle_tx-002",
        source_event_id=tx_id,
    )
    assert len(first) == len(second)


def test_pipeline_events_are_idempotent(db):
    entity = Entity(name="Test Co", onboarding_status=OnboardingStatus.APPROVED.value)
    db.add(entity)
    db.flush()
    dept = Department(name="Eng", entity_id=entity.id)
    user = User(
        name="U",
        email="u@test.com",
        entity_id=entity.id,
        password_hash=get_password_hash("x"),
    )
    db.add_all([dept, user])
    db.flush()
    program = SpendProgram(
        entity_id=entity.id,
        name="Default",
        limit_amount=Decimal("5000"),
        limit_type="MONTHLY",
    )
    db.add(program)
    db.flush()
    card = Card(
        entity_id=entity.id,
        owner_id=user.id,
        department_id=dept.id,
        spend_program_id=program.id,
        type="VIRTUAL",
        limit_amount=Decimal("1000"),
        status="ACTIVE",
        masked_pan="**** **** **** 1234",
        card_token="tok_test",
    )
    db.add(card)
    db.flush()
    tx = Transaction(
        id="tx-pipe-1",
        entity_id=entity.id,
        department_id=dept.id,
        card_id=card.id,
        amount=Decimal("25"),
        merchant_name="Test",
        merchant_mcc="4816",
        status="HELD",
    )
    db.add(tx)
    db.commit()

    e1 = emit_pipeline_event(db, entity.id, tx.id, "hold_created", tx.id)
    e2 = emit_pipeline_event(db, entity.id, tx.id, "hold_created", tx.id)
    db.commit()
    assert e1.id == e2.id

    events = db.query(PipelineEvent).filter(PipelineEvent.transaction_id == tx.id).all()
    assert len(events) == 1
    assert events[0].event_type in PIPELINE_EVENT_TYPES


def test_spend_program_limit_blocks_swipe(db):
    """Spend program aggregate limit is enforced separately from card limit."""
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    from app.database import get_db
    from app.entities_rbac.models import Role, UserRole
    from app.cards.models import CardRequest

    # Reuse fixtures from test_flow if available — inline minimal setup
    for role_id in ["ADMIN", "EMPLOYEE", "MANAGER"]:
        db.add(Role(id=role_id, name=role_id))
    entity = Entity(name="Limit Co", onboarding_status=OnboardingStatus.APPROVED.value)
    db.add(entity)
    db.flush()
    dept = Department(name="Sales", entity_id=entity.id)
    db.add(dept)
    db.flush()

    from app.entities_rbac.auth import get_password_hash
    admin = User(name="Admin", email="admin@limit.com", entity_id=entity.id, password_hash=get_password_hash("pw"))
    emp = User(name="Emp", email="emp@limit.com", entity_id=entity.id, password_hash=get_password_hash("pw"))
    db.add_all([admin, emp])
    db.flush()
    db.add(UserRole(user_id=admin.id, role_id="ADMIN", entity_id=entity.id))
    db.add(UserRole(user_id=emp.id, role_id="EMPLOYEE", entity_id=entity.id, department_id=dept.id))
    db.flush()

    program = SpendProgram(
        entity_id=entity.id,
        name="Tight Program",
        limit_amount=Decimal("300"),
        limit_type="MONTHLY",
    )
    db.add(program)
    db.flush()

    card = Card(
        entity_id=entity.id,
        owner_id=emp.id,
        department_id=dept.id,
        spend_program_id=program.id,
        type="VIRTUAL",
        limit_amount=Decimal("500"),
        status="ACTIVE",
        masked_pan="**** **** **** 9999",
        card_token="tok_limit",
    )
    db.add(card)
    db.commit()

    def override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as client:
        token = client.post("/api/auth/token", data={"username": "emp@limit.com", "password": "pw"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Entity-Id": entity.id}
        resp = client.post(
            "/api/transactions/simulate-swipe",
            headers=headers,
            json={
                "card_id": card.id,
                "amount": 350.0,
                "merchant_name": "Vendor",
                "merchant_mcc": "5411",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "DECLINED"
        assert resp.json()["decline_reason"] == "Exceeds spend program limit"
    fastapi_app.dependency_overrides.clear()
