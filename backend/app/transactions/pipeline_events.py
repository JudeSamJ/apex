"""Internal pipeline events emitted at each transaction state transition."""

import uuid
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app.transactions.models import PipelineEvent

logger = logging.getLogger(__name__)

PIPELINE_EVENT_TYPES = (
    "hold_created",
    "settled",
    "categorized",
    "approval_required",
    "approved",
    "rejected",
    "gl_coded",
    "sync_ready",
    "synced",
)


def emit_pipeline_event(
    db: Session,
    entity_id: str,
    transaction_id: str,
    event_type: str,
    source_event_id: str,
) -> PipelineEvent:
    if event_type not in PIPELINE_EVENT_TYPES:
        raise ValueError(f"Unknown pipeline event type: {event_type}")

    existing = db.query(PipelineEvent).filter(
        PipelineEvent.transaction_id == transaction_id,
        PipelineEvent.event_type == event_type,
        PipelineEvent.source_event_id == source_event_id,
    ).first()
    if existing:
        return existing

    event = PipelineEvent(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        transaction_id=transaction_id,
        event_type=event_type,
        source_event_id=source_event_id,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    db.flush()
    logger.info(
        "pipeline_event entity=%s tx=%s type=%s source_event_id=%s",
        entity_id,
        transaction_id,
        event_type,
        source_event_id,
    )
    return event
