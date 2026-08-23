import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, event, text
from sqlalchemy import pool

from alembic import context

# Make the "app" package importable regardless of the cwd alembic was
# invoked from (it's always the backend/ directory, one level up from here).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use this app's own DATABASE_URL resolution (secrets provider +
# postgres:// -> postgresql+psycopg:// normalization) instead of a second,
# easily-drifting copy hardcoded in alembic.ini.
from app.database import DATABASE_URL
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Import every model module so Base.metadata is fully populated —
# autogenerate can only see tables that have actually been imported.
from app.database import Base
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

target_metadata = Base.metadata

# This app only ever uses the "public" and "ledger" schemas — without this,
# autogenerate's include_schemas=True would also reflect (and try to diff
# against) Postgres system schemas like information_schema/pg_catalog.
_KNOWN_SCHEMAS = {"public", "ledger", None}


def _include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in _KNOWN_SCHEMAS
    if type_ == "table" and name == "alembic_version":
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"check_same_thread": False} if _is_sqlite() else {},
    )

    # SQLite has no real schemas — app.database.py works around this by
    # ATTACHing a second physical file as an alias named "ledger" on every
    # connection. Migrations that touch schema="ledger" tables (see
    # ledger/models.py) need that same alias to resolve locally.
    if _is_sqlite():
        @event.listens_for(connectable, "connect")
        def _attach_ledger(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("ATTACH DATABASE './ramp_ledger.db' AS ledger;")
            cursor.close()

    with connectable.connect() as connection:
        if not _is_sqlite():
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS public;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ledger;"))
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=_include_name,
            version_table_schema="public" if not _is_sqlite() else None,
            # SQLite's ALTER TABLE support is limited (no DROP/ALTER COLUMN);
            # batch mode rebuilds the table under the hood so migrations
            # written for Postgres still apply locally without hand-written
            # SQLite branches.
            render_as_batch=_is_sqlite(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
