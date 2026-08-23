from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
import uuid

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.transactions.models import Transaction
from app.cards.models import Card, CardRequest
from app.entities_rbac.models import Department
from app.reporting.models import Budget
from app.insights.models import Insight
from app.approvals.models import Approval, ApprovalStep
from app.bills.models import Bill, BillLineItem
from app.reimbursements.models import Reimbursement
from app.money import MoneyOut

router = APIRouter(prefix="/api/reporting", tags=["reporting"])

class BudgetCreate(BaseModel):
    department_id: Optional[str] = None
    category: Optional[str] = None
    period: str  # YYYY-MM
    amount: Decimal

class BudgetOut(BaseModel):
    id: str
    department_name: Optional[str] = None
    category: Optional[str] = None
    period: str
    amount: MoneyOut

class BudgetCompareOut(BaseModel):
    id: str
    department_name: Optional[str] = None
    category: Optional[str] = None
    period: str
    budgeted_amount: MoneyOut
    actual_amount: MoneyOut
    remaining_amount: MoneyOut

@router.get("/dashboard")
def get_dashboard_metrics(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    from collections import defaultdict
    from app.entities_rbac.models import Entity
    from app.fx.service import sum_converted

    entity_id = current_user.active_entity_id
    user_id = current_user.user_id
    base_currency = db.query(Entity.base_currency).filter(Entity.id == entity_id).scalar() or "USD"

    # Filter rules: Employees only see their own cards & transactions
    tx_filter = [Transaction.entity_id == entity_id, Transaction.status.in_(["HELD", "SETTLED"])]
    card_filter = [Card.entity_id == entity_id]
    request_filter = [CardRequest.entity_id == entity_id]

    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        tx_filter.append(Transaction.card_id.in_(
            db.query(Card.id).filter(Card.owner_id == user_id).subquery()
        ))
        card_filter.append(Card.owner_id == user_id)
        request_filter.append(CardRequest.requester_id == user_id)

    # A SQL-level SUM() can't respect per-row currency, so every aggregation
    # below fetches (amount, currency) and converts+sums in Python via
    # sum_converted rather than summing raw amounts across currencies.

    # 1. Overall Metrics
    spend_rows = db.query(Transaction.amount, Transaction.currency).filter(*tx_filter).all()
    total_spend = sum_converted(spend_rows, base_currency)
    active_cards_count = db.query(func.count(Card.id)).filter(*card_filter, Card.status == "ACTIVE").scalar() or 0
    pending_requests_count = db.query(func.count(CardRequest.id)).filter(*request_filter, CardRequest.status == "PENDING_APPROVAL").scalar() or 0

    # 2. Spend by Department (Entity wide for admins, otherwise only departments user can access)
    dept_rows = db.query(
        Department.name, Transaction.amount, Transaction.currency
    ).join(Transaction, Transaction.department_id == Department.id).filter(*tx_filter).all()
    dept_grouped = defaultdict(list)
    for name, amount, currency in dept_rows:
        dept_grouped[name].append((amount, currency))
    spend_by_dept = [
        {"department": name, "amount": float(sum_converted(rows, base_currency))}
        for name, rows in dept_grouped.items()
    ]

    # 3. Spend by Category
    cat_rows = db.query(Transaction.category, Transaction.amount, Transaction.currency).filter(*tx_filter).all()
    cat_grouped = defaultdict(list)
    for category, amount, currency in cat_rows:
        cat_grouped[category or "General Spend"].append((amount, currency))
    spend_by_category = [
        {"category": category, "amount": float(sum_converted(rows, base_currency))}
        for category, rows in cat_grouped.items()
    ]

    # 4. Spend Over Time (daily)
    time_rows = db.query(
        func.date(Transaction.created_at).label("day"), Transaction.amount, Transaction.currency
    ).filter(*tx_filter).all()
    time_grouped = defaultdict(list)
    for day, amount, currency in time_rows:
        day_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
        time_grouped[day_str].append((amount, currency))
    spend_over_time = [
        {"date": day_str, "amount": float(sum_converted(rows, base_currency))}
        for day_str, rows in sorted(time_grouped.items())
    ]

    return {
        "metrics": {
            "total_spend": float(total_spend),
            "active_cards": active_cards_count,
            "pending_requests": pending_requests_count,
            "currency": base_currency
        },
        "spend_by_department": spend_by_dept,
        "spend_by_category": spend_by_category,
        "spend_over_time": spend_over_time
    }

@router.post("/budgets", response_model=BudgetOut)
def create_budget(
    budget_in: BudgetCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can configure budgets")

    budget = Budget(
        id=str(uuid.uuid4()),
        entity_id=current_user.active_entity_id,
        department_id=budget_in.department_id,
        category=budget_in.category,
        period=budget_in.period,
        amount=budget_in.amount
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)

    dept_name = budget.department.name if budget.department else None
    return {
        "id": budget.id,
        "department_name": dept_name,
        "category": budget.category,
        "period": budget.period,
        "amount": budget.amount
    }

@router.get("/budgets", response_model=List[BudgetCompareOut])
def get_budgets_comparison(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    from app.entities_rbac.models import Entity
    from app.fx.service import sum_converted

    entity_id = current_user.active_entity_id
    base_currency = db.query(Entity.base_currency).filter(Entity.id == entity_id).scalar() or "USD"
    budgets = db.query(Budget).filter(Budget.entity_id == entity_id).all()

    out = []
    for b in budgets:
        # Calculate actual settled spend matching budget scope and period.
        # Period is "YYYY-MM"; budget.amount is denominated in the entity's
        # base_currency, so matching transactions (which may be in any
        # currency their card spends in) are converted before summing.
        period_format = func.strftime('%Y-%m', Transaction.created_at) if db.bind.dialect.name == "sqlite" else func.to_char(Transaction.created_at, 'YYYY-MM')

        q = db.query(Transaction.amount, Transaction.currency).filter(
            Transaction.entity_id == entity_id,
            Transaction.status == "SETTLED",
            period_format == b.period
        )

        if b.department_id:
            q = q.filter(Transaction.department_id == b.department_id)
        if b.category:
            q = q.filter(Transaction.category == b.category)

        actual_spend = sum_converted(q.all(), base_currency)

        dept_name = b.department.name if b.department else "All Departments"
        out.append({
            "id": b.id,
            "department_name": dept_name,
            "category": b.category or "All Categories",
            "period": b.period,
            "budgeted_amount": b.amount,
            "actual_amount": actual_spend,
            "remaining_amount": b.amount - actual_spend
        })
    return out

@router.get("/admin-kpis")
def get_admin_kpis(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    entity_id = current_user.active_entity_id
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Operational KPIs are restricted to Admins and Bookkeepers")

    # 1. Operational Efficiency
    # % of settled transactions auto-categorized + auto-GL coded without manual overrides
    # (For MVP, check if transaction settled status has category and gl_account_id set)
    total_tx = db.query(Transaction).filter(
        Transaction.entity_id == entity_id,
        Transaction.status == "SETTLED"
    ).count()

    auto_tx = db.query(Transaction).filter(
        Transaction.entity_id == entity_id,
        Transaction.status == "SETTLED",
        Transaction.category.isnot(None),
        Transaction.gl_account_id.isnot(None)
    ).count()

    efficiency = (auto_tx / total_tx * 100) if total_tx > 0 else 100.0

    # 2. Money Saved
    # rollup of potential_savings over CONFIRMED insights
    savings = db.query(func.sum(Insight.potential_savings)).filter(
        Insight.entity_id == entity_id,
        Insight.status == "CONFIRMED"
    ).scalar() or 0.00

    # 3. Compliance
    # Compliance metrics:
    # a. % of card transactions approved (within program limits)
    total_swipes = db.query(Transaction).filter(Transaction.entity_id == entity_id).count()
    approved_swipes = db.query(Transaction).filter(
        Transaction.entity_id == entity_id,
        Transaction.status.in_(["HELD", "SETTLED"])
    ).count()
    card_compliance = (approved_swipes / total_swipes * 100) if total_swipes > 0 else 100.0

    # b. % of paid bills with complete GL coding
    total_paid_bills = db.query(Bill).filter(
        Bill.entity_id == entity_id,
        Bill.status == "PAID"
    ).count()
    coded_paid_bills = db.query(Bill).filter(
        Bill.entity_id == entity_id,
        Bill.status == "PAID"
    ).join(Bill.line_items).filter(BillLineItem.gl_account_id.isnot(None)).distinct().count()
    
    bill_compliance = (coded_paid_bills / total_paid_bills * 100) if total_paid_bills > 0 else 100.0

    compliance = (card_compliance + bill_compliance) / 2

    # 4. Employee Experience
    # Average approval turnaround time in hours
    # Average duration: decided_at - approval.created_at
    steps = db.query(ApprovalStep).join(Approval).filter(
        Approval.entity_id == entity_id,
        ApprovalStep.decision != "PENDING",
        ApprovalStep.decided_at.isnot(None)
    ).all()

    total_hours = 0.0
    count = 0
    for s in steps:
        dt = s.decided_at - s.approval.created_at
        total_hours += dt.total_seconds() / 3600.0
        count += 1

    avg_turnaround_hours = (total_hours / count) if count > 0 else 1.5  # default/fallback to 1.5h if no approvals completed

    return {
        "operational_efficiency": round(efficiency, 1),
        "money_saved": float(savings),
        "compliance_score": round(compliance, 1),
        "avg_approval_turnaround_hours": round(avg_turnaround_hours, 1)
    }
