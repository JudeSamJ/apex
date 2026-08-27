# Must precede every other app import: it populates os.environ from
# backend/.env, and app.database resolves DATABASE_URL at import time.
import app.dotenv_bootstrap  # noqa: F401  (imported for its side effect)

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.observability import configure_logging, init_sentry, RequestIDMiddleware
from app.entities_rbac.router import router as auth_router
from app.cards.router import router as cards_router
from app.transactions.router import router as transactions_router
from app.reporting.router import router as reporting_router
from app.approvals.router import router as approvals_router
from app.bills.router import router as bills_router
from app.reimbursements.router import router as reimbursements_router
from app.accounting.router import router as accounting_router
from app.insights.router import router as insights_router
from app.audit_logs.router import router as audit_logs_router
from app.jobs.router import router as jobs_router
from app.webhooks.router import router as webhooks_router
from app.plaid.router import router as plaid_router
from app.qbo.router import router as qbo_router
from app.screening.router import router as screening_router
from app.disputes.router import router as disputes_router
from app.reconciliation.router import router as reconciliation_router
from app.notifications.router import router as notifications_router
from app.tax_reporting.router import router as tax_reporting_router
from app.ops.router import router as ops_router
from app.sso.router import router as sso_router
from app.fx.router import router as fx_router

configure_logging()
init_sentry()

# Browsers refuse a cross-origin response whose Access-Control-Allow-Origin
# does not name the calling page, and a deployed frontend is never on
# localhost. Set CORS_ORIGINS to a comma-separated list of exact origins the
# API should accept, e.g.
#
#   CORS_ORIGINS=https://apex-ten-phi.vercel.app
#
# Local dev origins stay allowed either way, so setting this in production
# does not break anyone running the app locally.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
CORS_ORIGINS = _DEV_ORIGINS + [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

# Preview deployments get a fresh URL per commit, so they cannot be listed
# ahead of time. Set CORS_ORIGIN_REGEX to match your own preview hosts, e.g.
#
#   CORS_ORIGIN_REGEX=https://apex-[a-z0-9-]+\.vercel\.app
#
# Keep it anchored to your project's own prefix. A bare .*\.vercel\.app would
# let any page on any Vercel account call this API with credentials attached.
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX") or None

app = FastAPI(title="Ramp Clone B2B Fintech Platform API", version="1.0.0")

app.add_middleware(RequestIDMiddleware)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers (X-Total-Count for paginated list endpoints)
    # aren't visible to browser JS via fetch()'s Response.headers unless
    # explicitly exposed — they're not in CORS's default safelist.
    expose_headers=["X-Total-Count"],
)

@app.on_event("startup")
def startup_event():
    # On a serverless host every cold start runs this, so each one would take
    # an Alembic upgrade check against the database before serving a byte, and
    # concurrent cold starts race each other. Set RUN_MIGRATIONS_ON_STARTUP
    # to a false value there and apply migrations as a deploy step instead.
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").strip().lower() in ("0", "false", "no"):
        logging.getLogger(__name__).info(
            "Skipping startup migrations (RUN_MIGRATIONS_ON_STARTUP is off); "
            "the database is expected to already be at head."
        )
        return
    init_db()

@app.get("/")
def read_root():
    return {"message": "Welcome to the B2B Fintech Platform API"}
    
app.include_router(auth_router)
app.include_router(cards_router)
app.include_router(transactions_router)
app.include_router(reporting_router)
app.include_router(approvals_router)
app.include_router(bills_router)
app.include_router(reimbursements_router)
app.include_router(accounting_router)
app.include_router(insights_router)
app.include_router(audit_logs_router)
app.include_router(jobs_router)
app.include_router(webhooks_router)
app.include_router(plaid_router)
app.include_router(qbo_router)
app.include_router(screening_router)
app.include_router(disputes_router)
app.include_router(reconciliation_router)
app.include_router(notifications_router)
app.include_router(tax_reporting_router)
app.include_router(ops_router)
app.include_router(sso_router)
app.include_router(fx_router)
