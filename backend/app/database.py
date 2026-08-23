import os
from sqlalchemy import create_engine, event
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
    """Bring the database schema up to date by applying every pending
    Alembic migration (backend/alembic/versions/) — the single source of
    truth for schema changes now, in place of the old Base.metadata.create_all()
    (which could only ever add brand-new tables, never alter an existing
    one, making every real schema change a manual DB wipe in practice).

    Safe to call on every app startup: a DB already at head is a no-op.
    """
    import logging
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))

    # A database can already hold this app's full table set without any
    # Alembic bookkeeping — e.g. one created by the old create_all() before
    # this migration setup existed, or (in this app's test suite) the dev
    # sqlite file that a TestClient's startup event touches independently
    # of each test's own isolated engine. In that case "upgrade" would try
    # to CREATE TABLE things that already exist and fail; what it actually
    # needs is to be told it's already at the baseline.
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "alembic_version" not in existing_tables and "entities" in existing_tables:
        logging.getLogger(__name__).warning(
            "Database has tables but no Alembic version — stamping as already "
            "at the baseline migration instead of trying to recreate them."
        )
        command.stamp(alembic_cfg, "head")

    command.upgrade(alembic_cfg, "head")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
