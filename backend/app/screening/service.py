import logging
from sqlalchemy.orm import Session

from app.screening.client import get_screening_client
from app.screening.models import SanctionsScreening

logger = logging.getLogger(__name__)


def screen_subject(db: Session, subject_type: str, subject_id: str, subject_name: str) -> SanctionsScreening:
    """Run a sanctions/watchlist screen on a name and persist the result as an
    audit record. Never raises on a provider failure — an ERROR record is
    stored instead, so a screening outage never blocks onboarding/vendor flows
    outright, but is still visible for manual follow-up."""
    client = get_screening_client()

    try:
        result = client.screen(subject_name)
        status = result["status"]
        provider = result["provider"]
        matches = result.get("matches")
    except Exception as e:
        logger.error(f"Sanctions screening errored for {subject_type} {subject_id} ('{subject_name}'): {e}")
        status = "ERROR"
        provider = "unknown"
        matches = {"error": str(e)}

    record = SanctionsScreening(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name=subject_name,
        provider=provider,
        status=status,
        match_details=matches,
    )
    db.add(record)
    db.flush()

    if status == "HIT":
        logger.warning(f"Sanctions screening HIT for {subject_type} {subject_id} ('{subject_name}')")

    return record


def latest_screening(db: Session, subject_type: str, subject_id: str):
    return (
        db.query(SanctionsScreening)
        .filter(SanctionsScreening.subject_type == subject_type, SanctionsScreening.subject_id == subject_id)
        .order_by(SanctionsScreening.created_at.desc())
        .first()
    )
