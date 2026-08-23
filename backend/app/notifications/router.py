from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.entities_rbac.auth import get_current_user_context, UserContext
from app.notifications.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: Optional[str] = None
    read: bool
    created_at: str


def _to_out(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "read": n.read,
        "created_at": n.created_at.isoformat(),
    }


@router.get("", response_model=List[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(
        Notification.entity_id == current_user.active_entity_id,
        Notification.user_id == current_user.user_id,
    )
    if unread_only:
        query = query.filter(Notification.read.is_(False))
    rows = query.order_by(Notification.created_at.desc()).all()
    return [_to_out(r) for r in rows]


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: str,
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    n = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.user_id,
        Notification.entity_id == current_user.active_entity_id,
    ).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read = True
    db.commit()
    db.refresh(n)
    return _to_out(n)


@router.post("/read-all")
def mark_all_read(
    current_user: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    updated = db.query(Notification).filter(
        Notification.entity_id == current_user.active_entity_id,
        Notification.user_id == current_user.user_id,
        Notification.read.is_(False),
    ).update({"read": True})
    db.commit()
    return {"marked_read": updated}
