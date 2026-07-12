from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.approvals.models import Approval, ApprovalStep, ApprovalState
from app.approvals.engine import ApprovalEngine

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

class DecisionIn(BaseModel):
    decision: str  # APPROVED or REJECTED
    comment: Optional[str] = None

class ApprovalStepOut(BaseModel):
    id: str
    approval_id: str
    approvable_type: str
    approvable_id: str
    step_number: int
    total_steps: int
    approver_role: str
    department_name: str
    created_at: str

@router.get("/inbox", response_model=List[ApprovalStepOut])
def get_approvals_inbox(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    # Fetch all pending steps for the active entity
    steps = db.query(ApprovalStep).join(Approval, ApprovalStep.approval_id == Approval.id).filter(
        Approval.entity_id == current_user.active_entity_id,
        ApprovalStep.decision == "PENDING",
        ApprovalStep.step_number == Approval.current_step,
        Approval.state.in_([ApprovalState.SUBMITTED, ApprovalState.IN_REVIEW])
    ).all()

    eligible_steps = []
    for step in steps:
        # Check authorization
        is_eligible = False
        role = step.approver_role
        
        if step.approver_id:
            is_eligible = (current_user.user_id == step.approver_id)
        elif role:
            if role in ["ADMIN", "AP_APPROVER"]:
                is_eligible = (role in current_user.roles)
            elif role == "MANAGER":
                # Scoped to department
                is_eligible = ("MANAGER" in current_user.roles and 
                               current_user.accessible_departments is not None and 
                               step.approval.department_id in current_user.accessible_departments)
            else:
                is_eligible = (role in current_user.roles)

        if is_eligible:
            eligible_steps.append({
                "id": step.id,
                "approval_id": step.approval_id,
                "approvable_type": step.approval.approvable_type,
                "approvable_id": step.approval.approvable_id,
                "step_number": step.step_number,
                "total_steps": step.approval.total_steps,
                "approver_role": step.approver_role or "",
                "department_name": step.approval.department.name,
                "created_at": step.approval.created_at.isoformat()
            })

    return eligible_steps

@router.post("/steps/{step_id}/decide")
def decide_approval_step(
    step_id: str,
    decision_in: DecisionIn,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    from app.rate_limit import check_rate_limit
    check_rate_limit(user_id=current_user.user_id, endpoint="decide_step")
    
    if decision_in.decision not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Decision must be APPROVED or REJECTED")

    # Get primary department of the user context
    from app.entities_rbac.models import UserRole
    ur = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.entity_id == current_user.active_entity_id
    ).first()
    user_dept_id = ur.department_id if ur else None

    approval = ApprovalEngine.decide_step(
        db=db,
        step_id=step_id,
        user_id=current_user.user_id,
        user_roles=current_user.roles,
        user_dept_id=user_dept_id,
        decision=decision_in.decision,
        comment=decision_in.comment
    )

    return {
        "message": f"Step decided as {decision_in.decision}",
        "approval_state": approval.state
    }
