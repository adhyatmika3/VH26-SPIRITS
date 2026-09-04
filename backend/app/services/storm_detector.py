from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.models.raw_alert import RawAlert


def detect_alert_storm(
    db: Session,
    current_time: datetime,
    window_seconds: Optional[int] = None,
    threshold: Optional[int] = None
) -> bool:
    """
    Evaluate if an alert storm condition is currently active.
    Calculates the velocity of raw alert arrivals within the sliding window.
    """
    window = window_seconds or settings.STORM_WINDOW_SECONDS
    burst_threshold = threshold or settings.STORM_ALERT_THRESHOLD
    cutoff_time = current_time - timedelta(seconds=window)

    stmt = (
        select(func.count(RawAlert.id))
        .where(RawAlert.received_at >= cutoff_time)
    )
    recent_count = db.execute(stmt).scalar() or 0

    is_storm = recent_count >= burst_threshold
    if is_storm:
        logger.warning(
            f"ALERT STORM ACTIVE! Ingested {recent_count} alerts in last {window}s "
            f"(threshold: {burst_threshold})"
        )

    return is_storm
