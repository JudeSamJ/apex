from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.cards.models import SpendProgram, Card, CardRequest
from app.cards.partner_client import get_issuing_client
from app.approvals.engine import ApprovalEngine

router = APIRouter(prefix="/api/cards", tags=["cards"])
partner_client = get_issuing_client()

class SpendProgramCreate(BaseModel):
    name: str
    limit_amount: Decimal
    limit_type: str  # MONTHLY, YEARLY, ONETIME
    allowed_mcc: Optional[List[str]] = None

class SpendProgramOut(BaseModel):
    id: str
    name: str
    limit_amount: Decimal
    limit_type: str
    allowed_mcc: Optional[List[str]] = None

class CardRequestCreate(BaseModel):
    spend_program_id: str
    type: str  # VIRTUAL, PHYSICAL
    limit_amount: Decimal

class CardRequestOut(BaseModel):
    id: str
    requester_name: str
    department_name: str
    spend_program_name: str
    type: str
    limit_amount: Decimal
    status: str
    created_at: str

class CardOut(BaseModel):
    id: str
    owner_name: str
    department_name: str
    spend_program_name: str
    type: str
    limit_amount: Decimal
    status: str
    masked_pan: str
    created_at: str

@router.post("/spend-programs", response_model=SpendProgramOut)
def create_spend_program(
    program_in: SpendProgramCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can create spend programs")
        
    program = SpendProgram(
        entity_id=current_user.active_entity_id,
        name=program_in.name,
        limit_amount=program_in.limit_amount,
        limit_type=program_in.limit_type,
        allowed_mcc=program_in.allowed_mcc
    )
    db.add(program)
    db.commit()
    db.refresh(program)
    return program

@router.get("/spend-programs", response_model=List[SpendProgramOut])
def list_spend_programs(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return db.query(SpendProgram).filter(SpendProgram.entity_id == current_user.active_entity_id).all()

@router.post("/request", response_model=CardRequestOut)
def request_card(
    request_in: CardRequestCreate,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    from app.rate_limit import check_rate_limit
    check_rate_limit(user_id=current_user.user_id, endpoint="card_request")
    
    # Verify spend program exists and belongs to active entity
    program = db.query(SpendProgram).filter(
        SpendProgram.id == request_in.spend_program_id,
        SpendProgram.entity_id == current_user.active_entity_id
    ).first()
    if not program:
        raise HTTPException(status_code=404, detail="Spend program not found")

    # If employee, they must request a card with limit <= spend program limit
    if request_in.limit_amount > program.limit_amount:
        raise HTTPException(status_code=400, detail="Requested limit exceeds spend program limit")

    # Find the user's primary department_id for this entity
    # We retrieve it from UserRole
    from app.entities_rbac.models import UserRole
    user_role = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.entity_id == current_user.active_entity_id
    ).first()
    
    department_id = user_role.department_id if user_role else None
    if not department_id:
        # Fallback to engineering or first department if user role doesn't define it
        from app.entities_rbac.models import Department
        first_dept = db.query(Department).filter(Department.entity_id == current_user.active_entity_id).first()
        if not first_dept:
            raise HTTPException(status_code=400, detail="No department set up for this entity")
        department_id = first_dept.id

    card_req = CardRequest(
        entity_id=current_user.active_entity_id,
        requester_id=current_user.user_id,
        department_id=department_id,
        spend_program_id=program.id,
        type=request_in.type,
        limit_amount=request_in.limit_amount,
        status="PENDING_APPROVAL"
    )
    db.add(card_req)
    db.flush()

    # Route through dynamic approvals engine
    from app.approvals.engine import ApprovalEngine
    ApprovalEngine.submit_for_approval(
        db=db,
        approvable_type="CARD_REQUEST",
        approvable_id=card_req.id,
        entity_id=card_req.entity_id,
        department_id=card_req.department_id,
        amount=card_req.limit_amount
    )
    db.commit()
    db.refresh(card_req)

    return {
        "id": card_req.id,
        "requester_name": current_user.name,
        "department_name": card_req.department.name,
        "spend_program_name": program.name,
        "type": card_req.type,
        "limit_amount": card_req.limit_amount,
        "status": card_req.status,
        "created_at": card_req.created_at.isoformat()
    }

@router.get("/requests", response_model=List[CardRequestOut])
def list_card_requests(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(CardRequest).filter(CardRequest.entity_id == current_user.active_entity_id)
    if not current_user.is_admin:
        # Employees can only see their own requests
        query = query.filter(CardRequest.requester_id == current_user.user_id)
        
    requests = query.all()
    out = []
    for r in requests:
        out.append({
            "id": r.id,
            "requester_name": r.requester.name,
            "department_name": r.department.name,
            "spend_program_name": r.spend_program.name,
            "type": r.type,
            "limit_amount": r.limit_amount,
            "status": r.status,
            "created_at": r.created_at.isoformat()
        })
    return out

@router.post("/requests/{request_id}/approve")
def approve_card_request(
    request_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    
    req = db.query(CardRequest).filter(
        CardRequest.id == request_id,
        CardRequest.entity_id == current_user.active_entity_id,
        CardRequest.status == "PENDING_APPROVAL"
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Pending card request not found")

    # Find the active pending step for this card request
    from app.approvals.models import Approval, ApprovalStep
    step = db.query(ApprovalStep).join(Approval).filter(
        Approval.approvable_type == "CARD_REQUEST",
        Approval.approvable_id == request_id,
        ApprovalStep.step_number == Approval.current_step,
        ApprovalStep.decision == "PENDING"
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="No active approval step found for this card request")

    # Get primary department of user context
    from app.entities_rbac.models import UserRole
    ur = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.entity_id == current_user.active_entity_id
    ).first()
    user_dept_id = ur.department_id if ur else None

    # Decide the step
    ApprovalEngine.decide_step(
        db=db,
        step_id=step.id,
        user_id=current_user.user_id,
        user_roles=current_user.roles,
        user_dept_id=user_dept_id,
        decision="APPROVED",
        comment="Approved via cards queue"
    )

    db.refresh(req)
    if req.status == "APPROVED":
        card = db.query(Card).filter(
            Card.entity_id == req.entity_id,
            Card.owner_id == req.requester_id,
            Card.spend_program_id == req.spend_program_id
        ).order_by(Card.created_at.desc()).first()
        if card:
            return {
                "id": card.id,
                "owner_name": card.owner.name,
                "department_name": card.department.name,
                "spend_program_name": card.spend_program.name,
                "type": card.type,
                "limit_amount": card.limit_amount,
                "status": card.status,
                "masked_pan": card.masked_pan,
                "created_at": card.created_at.isoformat()
            }
    return {
        "message": "Approval step processed",
        "status": req.status
    }

@router.post("/requests/{request_id}/reject")
def reject_card_request(
    request_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    
    req = db.query(CardRequest).filter(
        CardRequest.id == request_id,
        CardRequest.entity_id == current_user.active_entity_id,
        CardRequest.status == "PENDING_APPROVAL"
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Pending card request not found")

    # Find the active pending step for this card request
    from app.approvals.models import Approval, ApprovalStep
    step = db.query(ApprovalStep).join(Approval).filter(
        Approval.approvable_type == "CARD_REQUEST",
        Approval.approvable_id == request_id,
        ApprovalStep.step_number == Approval.current_step,
        ApprovalStep.decision == "PENDING"
    ).first()

    if not step:
        raise HTTPException(status_code=404, detail="No active approval step found for this card request")

    # Get primary department of user context
    from app.entities_rbac.models import UserRole
    ur = db.query(UserRole).filter(
        UserRole.user_id == current_user.user_id,
        UserRole.entity_id == current_user.active_entity_id
    ).first()
    user_dept_id = ur.department_id if ur else None

    # Decide the step
    ApprovalEngine.decide_step(
        db=db,
        step_id=step.id,
        user_id=current_user.user_id,
        user_roles=current_user.roles,
        user_dept_id=user_dept_id,
        decision="REJECTED",
        comment="Rejected via cards queue"
    )

    db.refresh(req)
    return {
        "message": "Approval step processed",
        "status": req.status
    }

@router.get("", response_model=List[CardOut])
def list_cards(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    query = db.query(Card).filter(Card.entity_id == current_user.active_entity_id)
    
    # If the user is not Admin/Bookkeeper, filter by user ownership
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        query = query.filter(Card.owner_id == current_user.user_id)
        
    cards = query.all()
    out = []
    for c in cards:
        out.append({
            "id": c.id,
            "owner_name": c.owner.name,
            "department_name": c.department.name,
            "spend_program_name": c.spend_program.name,
            "type": c.type,
            "limit_amount": c.limit_amount,
            "status": c.status,
            "masked_pan": c.masked_pan,
            "created_at": c.created_at.isoformat()
        })
    return out

@router.post("/{card_id}/freeze", response_model=CardOut)
def freeze_card(
    card_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    query = db.query(Card).filter(
        Card.id == card_id,
        Card.entity_id == current_user.active_entity_id
    )
    if not current_user.is_admin:
        query = query.filter(Card.owner_id == current_user.user_id)
        
    card = query.first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Call partner API synchronously
    partner_client.freeze_card(card.card_token)
    card.status = "FROZEN"
    
    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=card.entity_id,
        user_id=current_user.user_id,
        action="CARD_FREEZE",
        details={"card_id": card.id, "masked_pan": card.masked_pan}
    )
    
    db.commit()
    db.refresh(card)

    return {
        "id": card.id,
        "owner_name": card.owner.name,
        "department_name": card.department.name,
        "spend_program_name": card.spend_program.name,
        "type": card.type,
        "limit_amount": card.limit_amount,
        "status": card.status,
        "masked_pan": card.masked_pan,
        "created_at": card.created_at.isoformat()
    }

@router.post("/{card_id}/unfreeze", response_model=CardOut)
def unfreeze_card(
    card_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    query = db.query(Card).filter(
        Card.id == card_id,
        Card.entity_id == current_user.active_entity_id
    )
    if not current_user.is_admin:
        query = query.filter(Card.owner_id == current_user.user_id)
        
    card = query.first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Call partner API synchronously
    partner_client.unfreeze_card(card.card_token)
    card.status = "ACTIVE"
    
    from app.audit_logs.router import log_audit_action
    log_audit_action(
        db=db,
        entity_id=card.entity_id,
        user_id=current_user.user_id,
        action="CARD_UNFREEZE",
        details={"card_id": card.id, "masked_pan": card.masked_pan}
    )
    
    db.commit()
    db.refresh(card)

    return {
        "id": card.id,
        "owner_name": card.owner.name,
        "department_name": card.department.name,
        "spend_program_name": card.spend_program.name,
        "type": card.type,
        "limit_amount": card.limit_amount,
        "status": card.status,
        "masked_pan": card.masked_pan,
        "created_at": card.created_at.isoformat()
    }
