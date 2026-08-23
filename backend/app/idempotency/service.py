from typing import Any, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.idempotency.models import IdempotencyKey


class IdempotencyConflict(Exception):
    """Raised when a duplicate request arrives while the original is still in flight."""


class IdempotentReplay(Exception):
    """Raised to short-circuit a duplicate request with the original completed response."""

    def __init__(self, status_code: int, response_body: Any):
        self.status_code = status_code
        self.response_body = response_body


def begin_idempotent(
    db: Session, key: Optional[str], endpoint: str, entity_id: str
) -> Optional[IdempotencyKey]:
    """Reserve `key` for `endpoint`/`entity_id`, or resolve it against a prior attempt.

    Returns the placeholder record to pass to `complete_idempotent` when the
    caller should proceed and execute the action. Returns None when no key was
    supplied (idempotency is opt-in via the `Idempotency-Key` header).
    Raises `IdempotentReplay` when a completed response already exists for this
    key, and `IdempotencyConflict` when another request with the same key is
    still being processed.
    """
    if not key:
        return None

    record = IdempotencyKey(key=key, endpoint=endpoint, entity_id=entity_id)
    db.add(record)
    try:
        db.flush()
        return record
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(IdempotencyKey)
            .filter_by(key=key, endpoint=endpoint, entity_id=entity_id)
            .first()
        )
        if existing is not None and existing.response_body is not None:
            raise IdempotentReplay(existing.status_code, existing.response_body)
        raise IdempotencyConflict(
            f"Request with Idempotency-Key '{key}' is already being processed"
        )


def complete_idempotent(record: Optional[IdempotencyKey], status_code: int, response_body: Any) -> None:
    """Fill in the reserved record with the outcome so retries can replay it."""
    if record is None:
        return
    record.status_code = status_code
    record.response_body = response_body
