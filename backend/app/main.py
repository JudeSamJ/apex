from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
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

app = FastAPI(title="Ramp Clone B2B Fintech Platform API", version="1.0.0")

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
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
