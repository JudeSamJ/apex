from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.audit_logs.models import AuditLog

router = APIRouter(prefix="/api/reporting/audit-logs", tags=["audit-logs"])

class AuditLogOut(BaseModel):
    id: str
    action: str
    user_name: Optional[str] = None
    details: Optional[dict] = None
    created_at: str

def log_audit_action(db: Session, entity_id: str, user_id: Optional[str], action: str, details: dict):
    log = AuditLog(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        details=details,
        created_at=datetime.utcnow()
    )
    db.add(log)
    db.flush()

@router.get("", response_model=List[AuditLogOut])
def list_audit_logs(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    current_user.check_active_entity_approved()
    if not current_user.is_admin and "BOOKKEEPER" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Audit logs are restricted to Admins and Bookkeepers")

    logs = db.query(AuditLog).filter(
        AuditLog.entity_id == current_user.active_entity_id
    ).order_by(AuditLog.created_at.desc()).limit(100).all()

    out = []
    for l in logs:
        out.append({
            "id": l.id,
            "action": l.action,
            "user_name": l.user.name if l.user else "System",
            "details": l.details,
            "created_at": l.created_at.isoformat()
        })
    return out
