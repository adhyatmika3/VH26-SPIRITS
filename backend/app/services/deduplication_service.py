from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.models.canonical_alert import CanonicalAlert


def check_and_deduplicate(
    db: Session,
    fingerprint: str,
    current_time: datetime,
    window_seconds: Optional[int] = None
) -> Tuple[Optional[CanonicalAlert], bool]:
    """
    Concurrency-safe deduplication using row-level locking (SELECT ... FOR UPDATE).
    Checks if an active canonical alert exists within the deduplication window.
    If matched, increments its occurrence count, updates last_seen timestamp, and returns (CanonicalAlert, True).
    If no match, returns (None, False).
    """
    window = window_seconds or settings.DEDUP_WINDOW_SECONDS
    cutoff_time = current_time - timedelta(seconds=window)

    # Concurrency-safe lookup with row-level lock on matching index
    stmt = (
        select(CanonicalAlert)
        .where(
            CanonicalAlert.fingerprint == fingerprint,
            CanonicalAlert.last_seen >= cutoff_time
        )
        .order_by(CanonicalAlert.last_seen.desc())
        .limit(1)
        .with_for_update()
    )
    existing_alert = db.execute(stmt).scalar_one_or_none()

    if existing_alert:
        # Match found within sliding temporal window -> Deduplicate
        existing_alert.occurrence_count += 1
        existing_alert.last_seen = current_time
        existing_alert.is_duplicate = True
        db.add(existing_alert)
        db.flush()

        logger.info(
            f"Deduplicated alert [fingerprint={fingerprint[:8]}, "
            f"service={existing_alert.service}, total_occurrences={existing_alert.occurrence_count}]"
        )
        return existing_alert, True

    # New distinct alert event
    return None, False
