from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status
import uuid

from app.approvals.models import Approval, ApprovalStep, ApprovalRule, ApprovalState

class ApprovalEngine:
    @staticmethod
    def submit_for_approval(
        db: Session,
        approvable_type: str,
        approvable_id: str,
        entity_id: str,
        department_id: str,
        amount: Decimal
    ) -> Approval:
        # 1. Look for matching approval rules
        rule = db.query(ApprovalRule).filter(
            ApprovalRule.entity_id == entity_id,
            ApprovalRule.applies_to == approvable_type,
            ApprovalRule.min_amount <= amount,
            or_(ApprovalRule.max_amount >= amount, ApprovalRule.max_amount.is_(None))
        ).first()

        # Fallback defaults if no rule matches
        if rule:
            steps_needed = rule.required_steps  # Expected format: List of roles/strings, e.g. ["MANAGER", "ADMIN"]
        else:
            if approvable_type == "CARD_REQUEST":
                # Card requests require Admin review by default if limit > 2000, else Manager
                steps_needed = ["MANAGER", "ADMIN"] if amount > 2000 else ["MANAGER"]
            elif approvable_type == "BILL":
                # Bills require Admin by default
                steps_needed = ["ADMIN"]
            else:
                # Reimbursements require Manager
                steps_needed = ["MANAGER"]

        # 2. Create the Approval record
        approval = Approval(
            id=str(uuid.uuid4()),
            approvable_type=approvable_type,
            approvable_id=approvable_id,
            entity_id=entity_id,
            department_id=department_id,
            current_step=1,
            total_steps=len(steps_needed),
            state=ApprovalState.SUBMITTED
        )
        db.add(approval)
        db.flush()

        # 3. Create the Approval steps
        for idx, role_name in enumerate(steps_needed):
            step = ApprovalStep(
                id=str(uuid.uuid4()),
                approval_id=approval.id,
                entity_id=approval.entity_id,
                step_number=idx + 1,
                approver_role=role_name,
                decision="PENDING"
            )
            db.add(step)

        db.commit()

        # Notify whoever can act on the first step — nothing to notify for
        # later steps until the approval actually reaches them.
        from app.notifications.service import notify_users_with_role
        notify_users_with_role(
            db=db,
            entity_id=approval.entity_id,
            role_id=steps_needed[0],
            type="APPROVAL_REQUESTED",
            title=f"{approvable_type.replace('_', ' ').title()} awaiting your approval",
            body=f"A {approvable_type.lower().replace('_', ' ')} (amount ${amount}) needs your review.",
        )
        db.commit()

        return approval

    @staticmethod
    def decide_step(
        db: Session,
        step_id: str,
        user_id: str,
        user_roles: List[str],
        user_dept_id: Optional[str],
        decision: str,
        comment: Optional[str] = None
    ) -> Approval:
        step = db.query(ApprovalStep).filter(ApprovalStep.id == step_id).first()
        if not step:
            raise HTTPException(status_code=404, detail="Approval step not found")

        approval = step.approval

        # Validate step eligibility
        if step.decision != "PENDING":
            raise HTTPException(status_code=400, detail="Step has already been decided")

        # Validate step order: can only decide the active current step
        if step.step_number != approval.current_step:
            raise HTTPException(status_code=400, detail="This step is not currently active in review")

        # Authorize: check if user matches the step criteria
        is_authorized = False
        if "ADMIN" in user_roles:
            is_authorized = True
        elif step.approver_id:
            is_authorized = (user_id == step.approver_id)
        elif step.approver_role:
            # If Admin or AP Approver or Bookkeeper: role matches entity wide
            if step.approver_role in ["ADMIN", "AP_APPROVER"]:
                is_authorized = (step.approver_role in user_roles)
            elif step.approver_role == "MANAGER":
                # Managers are scoped to their department
                is_authorized = ("MANAGER" in user_roles and user_dept_id == approval.department_id)
            else:
                is_authorized = (step.approver_role in user_roles)

        if not is_authorized:
            raise HTTPException(status_code=403, detail="You do not have the required role or department scope to approve this step")

        # Update step decision
        step.decision = decision
        step.decided_at = datetime.utcnow()
        step.comment = comment
        step.approver_id = user_id

        # Update Approval State Machine
        if decision == "REJECTED":
            approval.state = ApprovalState.REJECTED
            trigger_rejection_callback(db, approval, comment)
        elif decision == "APPROVED":
            if approval.current_step < approval.total_steps:
                approval.current_step += 1
                approval.state = ApprovalState.IN_REVIEW
            else:
                approval.state = ApprovalState.APPROVED
                trigger_approval_callback(db, approval)

        # Audit log decision
        from app.audit_logs.router import log_audit_action
        log_audit_action(
            db=db,
            entity_id=approval.entity_id,
            user_id=user_id,
            action="APPROVAL_DECISION",
            details={
                "approval_id": approval.id,
                "approvable_type": approval.approvable_type,
                "approvable_id": approval.approvable_id,
                "step_number": step.step_number,
                "decision": decision,
                "comment": comment
            }
        )

        db.commit()
        return approval

def trigger_approval_callback(db: Session, approval: Approval):
    if approval.approvable_type == "CARD_REQUEST":
        from app.cards.models import CardRequest, Card
        from app.cards.partner_client import get_issuing_client

        req = db.query(CardRequest).filter(CardRequest.id == approval.approvable_id).first()
        if req and req.status == "PENDING_APPROVAL":
            req.status = "APPROVED"
            partner_client = get_issuing_client()
            res = partner_client.create_card(req.entity_id, req.requester_id, req.type, float(req.limit_amount))
            card = Card(
                entity_id=req.entity_id,
                owner_id=req.requester_id,
                department_id=req.department_id,
                spend_program_id=req.spend_program_id,
                type=req.type,
                limit_amount=req.limit_amount,
                currency=req.currency,
                status="ACTIVE",
                masked_pan=res["masked_pan"],
                card_token=res["card_token"]
            )
            db.add(card)

    elif approval.approvable_type == "BILL":
        from app.bills.models import Bill
        bill = db.query(Bill).filter(Bill.id == approval.approvable_id).first()
        if bill:
            bill.status = "APPROVED"

    elif approval.approvable_type == "REIMBURSEMENT":
        from app.reimbursements.models import Reimbursement
        reimb = db.query(Reimbursement).filter(Reimbursement.id == approval.approvable_id).first()
        if reimb:
            reimb.status = "APPROVED"

def trigger_rejection_callback(db: Session, approval: Approval, comment: Optional[str]):
    if approval.approvable_type == "CARD_REQUEST":
        from app.cards.models import CardRequest
        req = db.query(CardRequest).filter(CardRequest.id == approval.approvable_id).first()
        if req:
            req.status = "REJECTED"
            
    elif approval.approvable_type == "BILL":
        from app.bills.models import Bill
        bill = db.query(Bill).filter(Bill.id == approval.approvable_id).first()
        if bill:
            # Rejected bill returns to DRAFT
            bill.status = "DRAFT"

    elif approval.approvable_type == "REIMBURSEMENT":
        from app.reimbursements.models import Reimbursement
        reimb = db.query(Reimbursement).filter(Reimbursement.id == approval.approvable_id).first()
        if reimb:
            reimb.status = "REJECTED"
