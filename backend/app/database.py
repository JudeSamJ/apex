import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.secrets.provider import get_secret

# DATABASE_URL commonly embeds credentials (postgresql://user:pass@host/db),
# so it goes through the secrets provider rather than a bare os.getenv().
DATABASE_URL = get_secret("DATABASE_URL", "sqlite:///./ramp_clone.db")

# Cloud Postgres providers (Neon, Supabase, RDS, ...) hand out plain
# postgres:// or postgresql:// URLs, but this app's driver is psycopg3
# (see requirements.txt) which SQLAlchemy only selects via the
# "postgresql+psycopg://" dialect prefix — normalize it here so a
# connection string pasted straight from a provider's dashboard just works.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# If using SQLite, automatically attach an in-memory database named 'ledger' for every connection
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE './ramp_ledger.db' AS ledger;")
        cursor.close()

def init_db():
    with engine.begin() as conn:
        if not DATABASE_URL.startswith("sqlite"):
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS public;"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ledger;"))
    
    # Import all models to register them on Base
    from app.entities_rbac.models import Entity, Department, Location, User, Role, UserRole
    from app.ledger.models import LedgerEntry, BalanceSnapshot
    from app.cards.models import SpendProgram, Card, CardRequest
    from app.transactions.models import Transaction, PipelineEvent, TransactionReceipt
    from app.approvals.models import Approval, ApprovalStep, ApprovalRule
    from app.bills.models import Vendor, VendorContact, VendorBankAccount, Bill, BillLineItem, BillPayment
    from app.reimbursements.models import Reimbursement, ReimbursementLineItem, MileageTrip, TripWaypoint
    from app.accounting.models import GLAccount, GLMapping, SyncQueue, AccountingCustomField
    from app.insights.models import MerchantNormalization, Insight
    from app.reporting.models import Budget
    from app.audit_logs.models import AuditLog
    from app.jobs.models import BackgroundJob
    from app.idempotency.models import IdempotencyKey
    from app.screening.models import SanctionsScreening
    from app.disputes.models import CardDispute
    from app.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy
    from app.notifications.models import Notification
    from app.sso.models import SSOConnection
    
    # Create tables
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
