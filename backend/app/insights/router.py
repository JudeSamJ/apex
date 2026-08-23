from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
import uuid
from datetime import datetime, timedelta

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.insights.models import MerchantNormalization, Insight
from app.transactions.models import Transaction
from app.money import MoneyOut

router = APIRouter(prefix="/api/insights", tags=["insights"])

class InsightOut(BaseModel):
    id: str
    type: str
    status: str
    severity: str
    description: str
    potential_savings: MoneyOut
    created_at: str

def normalize_merchant(name: str) -> str:
    n = name.lower().strip()
    if "aws" in n or "amazon web services" in n:
        return "AWS"
    if "google" in n or "gcp" in n or "gsuite" in n:
        return "Google"
    if "uber" in n:
        return "Uber"
    if "github" in n:
        return "GitHub"
    if "slack" in n:
        return "Slack"
    return " ".join(w.capitalize() for w in n.split())

@router.post("/detect")
def trigger_anomaly_detection(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    entity_id = current_user.active_entity_id

    # 1. Fetch settled transactions
    txs = db.query(Transaction).filter(
        Transaction.entity_id == entity_id,
        Transaction.status == "SETTLED"
    ).order_by(Transaction.created_at.asc()).all()

    # 2. Populate Normalizations and map tx to normalized names
    normalized_txs = []
    for tx in txs:
        norm = db.query(MerchantNormalization).filter(
            MerchantNormalization.entity_id == entity_id,
            MerchantNormalization.raw_name == tx.merchant_name
        ).first()

        if not norm:
            norm = MerchantNormalization(
                id=str(uuid.uuid4()),
                entity_id=entity_id,
                raw_name=tx.merchant_name,
                normalized_name=normalize_merchant(tx.merchant_name)
            )
            db.add(norm)
            db.flush()

        normalized_txs.append({
            "tx": tx,
            "norm_name": norm.normalized_name
        })

    insights_created = 0

    # 3. Detect duplicate subscriptions:
    # Charged twice for the same amount, on the same card, within 30 days
    card_merchant_groups = {}
    for item in normalized_txs:
        tx = item["tx"]
        key = (tx.card_id, item["norm_name"], tx.amount)
        if key not in card_merchant_groups:
            card_merchant_groups[key] = []
        card_merchant_groups[key].append(tx)

    for key, group in card_merchant_groups.items():
        card_id, norm_name, amount = key
        if len(group) < 2:
            continue
        
        # Sort group by created_at
        group.sort(key=lambda x: x.created_at)
        for i in range(len(group) - 1):
            tx1 = group[i]
            tx2 = group[i+1]
            diff = tx2.created_at - tx1.created_at
            if diff.days <= 30:
                # Flag duplicate subscription
                desc = f"Potential duplicate subscription: card charged twice for ${amount:.2f} by {norm_name} within {diff.days} days."
                
                # Check duplicate insight
                existing = db.query(Insight).filter(
                    Insight.entity_id == entity_id,
                    Insight.type == "DUPLICATE_SUBSCRIPTION",
                    Insight.description == desc
                ).first()

                if not existing:
                    insight = Insight(
                        id=str(uuid.uuid4()),
                        entity_id=entity_id,
                        type="DUPLICATE_SUBSCRIPTION",
                        status="OPEN",
                        severity="MEDIUM",
                        description=desc,
                        potential_savings=amount,
                        details={"tx_id_1": tx1.id, "tx_id_2": tx2.id}
                    )
                    db.add(insight)
                    insights_created += 1

    # 4. Detect Price Increases:
    # Monthly cost for same normalized merchant on same card went up
    card_merchant_history = {}
    for item in normalized_txs:
        tx = item["tx"]
        key = (tx.card_id, item["norm_name"])
        if key not in card_merchant_history:
            card_merchant_history[key] = []
        card_merchant_history[key].append(tx)

    for key, group in card_merchant_history.items():
        card_id, norm_name = key
        if len(group) < 2:
            continue

        # Sort by date
        group.sort(key=lambda x: x.created_at)
        for i in range(len(group) - 1):
            tx1 = group[i]
            tx2 = group[i+1]
            diff = tx2.created_at - tx1.created_at
            # Spaced approximately monthly (between 15 and 45 days)
            if 15 <= diff.days <= 45:
                if tx2.amount > tx1.amount:
                    diff_amt = tx2.amount - tx1.amount
                    desc = f"Price increase detected: monthly subscription cost for {norm_name} rose from ${tx1.amount:.2f} to ${tx2.amount:.2f} (Increase of ${diff_amt:.2f})."
                    
                    existing = db.query(Insight).filter(
                        Insight.entity_id == entity_id,
                        Insight.type == "PRICE_INCREASE",
                        Insight.description == desc
                    ).first()

                    if not existing:
                        insight = Insight(
                            id=str(uuid.uuid4()),
                            entity_id=entity_id,
                            type="PRICE_INCREASE",
                            status="OPEN",
                            severity="LOW",
                            description=desc,
                            potential_savings=diff_amt,
                            details={"tx_id_1": tx1.id, "tx_id_2": tx2.id, "diff": float(diff_amt)}
                        )
                        db.add(insight)
                        insights_created += 1

    db.commit()
    return {"message": "Anomaly detection run complete", "insights_created": insights_created}

@router.get("", response_model=List[InsightOut])
def list_insights(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    insights = db.query(Insight).filter(Insight.entity_id == current_user.active_entity_id).all()
    out = []
    for ins in insights:
        out.append({
            "id": ins.id,
            "type": ins.type,
            "status": ins.status,
            "severity": ins.severity,
            "description": ins.description,
            "potential_savings": ins.potential_savings,
            "created_at": ins.created_at.isoformat()
        })
    return out

@router.post("/{id}/confirm")
def confirm_insight(
    id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    insight = db.query(Insight).filter(
        Insight.id == id,
        Insight.entity_id == current_user.active_entity_id
    ).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    insight.status = "CONFIRMED"
    db.commit()
    return {"message": "Insight confirmed, savings verified"}

@router.post("/{id}/dismiss")
def dismiss_insight(
    id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    insight = db.query(Insight).filter(
        Insight.id == id,
        Insight.entity_id == current_user.active_entity_id
    ).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    insight.status = "DISMISSED"
    db.commit()
    return {"message": "Insight dismissed"}

@router.get("/savings-summary")
def get_total_savings(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    # Sum potential_savings over CONFIRMED insights
    savings = db.query(func.sum(Insight.potential_savings)).filter(
        Insight.entity_id == current_user.active_entity_id,
        Insight.status == "CONFIRMED"
    ).scalar()
    
    return {"total_savings": float(savings or 0.00)}
