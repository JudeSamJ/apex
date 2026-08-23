import logging
from typing import Iterable, Optional
from sqlalchemy.orm import Session

from app.notifications.client import get_email_client
from app.notifications.models import Notification

logger = logging.getLogger(__name__)


def notify(
    db: Session,
    entity_id: str,
    user_id: str,
    type: str,
    title: str,
    body: Optional[str] = None,
    send_email: bool = False,
) -> Notification:
    """Create an in-app notification and, if requested, best-effort email it.

    A failed email never blocks the caller — the in-app notification always
    lands, and the send failure is only logged. Callers that trigger this
    from inside a larger transaction (approval routing, webhook handling)
    shouldn't have that transaction fail just because SMTP is down.
    """
    notification = Notification(
        entity_id=entity_id,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
    )
    db.add(notification)
    db.flush()

    if send_email:
        try:
            from app.entities_rbac.models import User
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                get_email_client().send(to=user.email, subject=title, body=body or "")
                notification.email_sent = True
        except Exception as e:
            logger.warning(f"Failed to email notification {notification.id} to user {user_id}: {e}")

    return notification


def notify_users_with_role(
    db: Session,
    entity_id: str,
    role_id: str,
    type: str,
    title: str,
    body: Optional[str] = None,
    send_email: bool = False,
) -> None:
    """Notify every user holding `role_id` in `entity_id` — the common case
    of "tell whoever can act on this" (approvers, admins reviewing a hit)."""
    from app.entities_rbac.models import UserRole

    user_ids: Iterable[str] = {
        ur.user_id
        for ur in db.query(UserRole).filter(UserRole.entity_id == entity_id, UserRole.role_id == role_id).all()
    }
    for user_id in user_ids:
        notify(db, entity_id, user_id, type, title, body, send_email=send_email)
