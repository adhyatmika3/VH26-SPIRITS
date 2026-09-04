from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case, and_
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.decision_record import DecisionRecord
from app.models.incident import Incident
from app.models.notification_record import NotificationRecord
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    SeverityDistributionItem,
    IncidentPriorityDistributionItem,
    SourceDistributionItem,
    ServiceDistributionItem,
    NoisyServiceItem,
    TimelinePoint,
    DecisionDistributionResponse
)
from app.core.config import settings
from app.core.logging import logger


def parse_time_range(
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parses time_range ('15m', '1h', '6h', '24h', '7d', '30d') or explicit start_time and end_time.
    Returns timezone-aware UTC datetime boundaries.
    """
    now = datetime.now(timezone.utc)

    if start_time and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if start_time or end_time:
        return start_time, (end_time or now)

    if not time_range:
        return None, None

    range_clean = time_range.strip().lower()
    if range_clean in ("15m", "15min"):
        return now - timedelta(minutes=15), now
    elif range_clean == "1h":
        return now - timedelta(hours=1), now
    elif range_clean in ("6h", "6hr"):
        return now - timedelta(hours=6), now
    elif range_clean in ("24h", "1d"):
        return now - timedelta(hours=24), now
    elif range_clean == "7d":
        return now - timedelta(days=7), now
    elif range_clean == "30d":
        return now - timedelta(days=30), now

    return None, None


def get_analytics_overview(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> AnalyticsOverviewResponse:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    # 1. Total Raw Ingested Alerts
    raw_query = db.query(func.count(RawAlert.id))
    if start_dt:
        raw_query = raw_query.filter(RawAlert.received_at >= start_dt)
    if end_dt:
        raw_query = raw_query.filter(RawAlert.received_at <= end_dt)
    total_alerts = raw_query.scalar() or 0

    # 2. Decision breakdown & average processing time
    dec_filters = []
    if start_dt:
        dec_filters.append(DecisionRecord.created_at >= start_dt)
    if end_dt:
        dec_filters.append(DecisionRecord.created_at <= end_dt)

    dec_stats = (
        db.query(
            func.count(DecisionRecord.id).label("total_processed"),
            func.sum(case((DecisionRecord.decision == "SUPPRESS", 1), else_=0)).label("suppressed"),
            func.sum(case((DecisionRecord.decision == "NOTIFY", 1), else_=0)).label("notified"),
            func.sum(case((DecisionRecord.decision == "ESCALATE", 1), else_=0)).label("escalated"),
            func.avg(DecisionRecord.processing_time_ms).label("avg_latency")
        )
        .filter(*dec_filters)
        .first()
    )

    processed_alerts = int(dec_stats.total_processed or 0)
    suppressed_alerts = int(dec_stats.suppressed or 0)
    notified_alerts = int(dec_stats.notified or 0)
    escalated_alerts = int(dec_stats.escalated or 0)
    avg_latency = float(dec_stats.avg_latency or 0.0)

    # If raw total is 0 but processed > 0 (e.g. from direct tests), fall back to processed
    effective_total = max(total_alerts, processed_alerts)

    # Rates with zero division safety
    suppression_rate = round((suppressed_alerts / effective_total * 100.0), 2) if effective_total > 0 else 0.0
    notification_rate = round((notified_alerts / effective_total * 100.0), 2) if effective_total > 0 else 0.0
    escalation_rate = round((escalated_alerts / effective_total * 100.0), 2) if effective_total > 0 else 0.0

    # Calculate real active deduplication fingerprint pool within sliding window
    now_utc = datetime.now(timezone.utc)
    dedup_cutoff = now_utc - timedelta(seconds=settings.DEDUP_WINDOW_SECONDS)
    active_dedupe_pool = (
        db.query(func.count(func.distinct(CanonicalAlert.fingerprint)))
        .filter(CanonicalAlert.last_seen >= dedup_cutoff)
        .scalar() or 0
    )

    return AnalyticsOverviewResponse(
        total_alerts=effective_total,
        processed_alerts=processed_alerts,
        suppressed_alerts=suppressed_alerts,
        notified_alerts=notified_alerts,
        escalated_alerts=escalated_alerts,
        suppression_rate=suppression_rate,
        notification_rate=notification_rate,
        escalation_rate=escalation_rate,
        alert_reduction=suppressed_alerts,
        average_processing_time_ms=round(avg_latency, 2),
        active_dedupe_pool=int(active_dedupe_pool)
    )


def get_alerts_by_severity(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[SeverityDistributionItem]:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    query = db.query(CanonicalAlert.severity, func.count(CanonicalAlert.id).label("count"))
    if start_dt:
        query = query.filter(CanonicalAlert.created_at >= start_dt)
    if end_dt:
        query = query.filter(CanonicalAlert.created_at <= end_dt)

    results = query.group_by(CanonicalAlert.severity).all()
    total_count = sum(r.count for r in results) or 1

    return [
        SeverityDistributionItem(
            severity=r.severity or "UNKNOWN",
            count=r.count,
            percentage=round((r.count / total_count * 100.0), 2)
        )
        for r in results
    ]


def get_incidents_by_priority(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[IncidentPriorityDistributionItem]:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    query = db.query(Incident.priority, func.count(Incident.id).label("count"))
    if start_dt:
        query = query.filter(Incident.created_at >= start_dt)
    if end_dt:
        query = query.filter(Incident.created_at <= end_dt)

    results = query.group_by(Incident.priority).all()
    counts = {r[0].upper() if r[0] else "LOW": int(r[1]) for r in results}
    total_count = sum(counts.values()) or 0

    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    return [
        IncidentPriorityDistributionItem(
            priority=p,
            count=counts.get(p, 0),
            percentage=round((counts.get(p, 0) / total_count * 100.0), 2) if total_count > 0 else 0.0
        )
        for p in order
    ]


def get_alerts_by_source(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[SourceDistributionItem]:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    query = db.query(CanonicalAlert.source, func.count(CanonicalAlert.id).label("count"))
    if start_dt:
        query = query.filter(CanonicalAlert.created_at >= start_dt)
    if end_dt:
        query = query.filter(CanonicalAlert.created_at <= end_dt)

    results = query.group_by(CanonicalAlert.source).all()
    total_count = sum(r.count for r in results) or 1

    return [
        SourceDistributionItem(
            source=r.source or "unknown",
            count=r.count,
            percentage=round((r.count / total_count * 100.0), 2)
        )
        for r in results
    ]


def get_alerts_by_service(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[ServiceDistributionItem]:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    query = db.query(CanonicalAlert.service, func.count(CanonicalAlert.id).label("count"))
    if start_dt:
        query = query.filter(CanonicalAlert.created_at >= start_dt)
    if end_dt:
        query = query.filter(CanonicalAlert.created_at <= end_dt)

    results = query.group_by(CanonicalAlert.service).order_by(desc("count")).all()
    total_count = sum(r.count for r in results) or 1

    return [
        ServiceDistributionItem(
            service=r.service or "unknown",
            count=r.count,
            percentage=round((r.count / total_count * 100.0), 2)
        )
        for r in results
    ]


def get_noisy_services(
    db: Session,
    limit: int = 10,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[NoisyServiceItem]:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    filters = []
    if start_dt:
        filters.append(DecisionRecord.created_at >= start_dt)
    if end_dt:
        filters.append(DecisionRecord.created_at <= end_dt)

    # Join DecisionRecord with CanonicalAlert to rank by alert volume
    results = (
        db.query(
            CanonicalAlert.service,
            func.count(DecisionRecord.id).label("total_alerts"),
            func.sum(case((DecisionRecord.decision == "SUPPRESS", 1), else_=0)).label("suppressed_count"),
            func.sum(case((DecisionRecord.decision == "NOTIFY", 1), else_=0)).label("notified_count"),
            func.sum(case((DecisionRecord.decision == "ESCALATE", 1), else_=0)).label("escalated_count")
        )
        .join(CanonicalAlert, DecisionRecord.canonical_alert_id == CanonicalAlert.id)
        .filter(*filters)
        .group_by(CanonicalAlert.service)
        .order_by(desc("total_alerts"))
        .limit(limit)
        .all()
    )

    items = []
    for r in results:
        tot = int(r.total_alerts or 0)
        sup = int(r.suppressed_count or 0)
        notif = int(r.notified_count or 0)
        esc = int(r.escalated_count or 0)
        sup_rate = round((sup / tot * 100.0), 2) if tot > 0 else 0.0

        items.append(
            NoisyServiceItem(
                service=r.service or "unknown",
                total_alerts=tot,
                suppressed_count=sup,
                notified_count=notif,
                escalated_count=esc,
                suppression_rate=sup_rate
            )
        )
    return items


def get_timeline(
    db: Session,
    interval: str = "hour",
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[TimelinePoint]:
    """
    Returns time-bucketed analytics over the specified range.
    Interval supports 'minute', 'hour', 'day'.
    """
    valid_intervals = {"minute", "hour", "day"}
    safe_interval = interval.lower() if interval.lower() in valid_intervals else "hour"

    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    filters = []
    if start_dt:
        filters.append(DecisionRecord.created_at >= start_dt)
    if end_dt:
        filters.append(DecisionRecord.created_at <= end_dt)

    dialect_name = getattr(db.bind.dialect, "name", "postgresql") if db.bind else "postgresql"
    if dialect_name == "sqlite":
        if safe_interval == "minute":
            fmt = "%Y-%m-%dT%H:%M:00Z"
        elif safe_interval == "day":
            fmt = "%Y-%m-%d 00:00:00Z"
        else:
            fmt = "%Y-%m-%dT%H:00:00Z"
        bucket_col = func.strftime(fmt, DecisionRecord.created_at).label("bucket")
    else:
        bucket_col = func.date_trunc(safe_interval, DecisionRecord.created_at).label("bucket")

    results = (
        db.query(
            bucket_col,
            func.count(DecisionRecord.id).label("received"),
            func.sum(case((DecisionRecord.decision == "SUPPRESS", 1), else_=0)).label("suppressed"),
            func.sum(case((DecisionRecord.decision == "NOTIFY", 1), else_=0)).label("notified"),
            func.sum(case((DecisionRecord.decision == "ESCALATE", 1), else_=0)).label("escalated")
        )
        .filter(*filters)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    timeline = []
    for r in results:
        if r.bucket is None:
            ts_str = datetime.now(timezone.utc).isoformat()
        elif hasattr(r.bucket, "isoformat"):
            ts_str = r.bucket.isoformat()
        else:
            ts_str = str(r.bucket)
        timeline.append(
            TimelinePoint(
                timestamp=ts_str,
                received=int(r.received or 0),
                suppressed=int(r.suppressed or 0),
                notified=int(r.notified or 0),
                escalated=int(r.escalated or 0)
            )
        )
    return timeline


def get_decisions_distribution(
    db: Session,
    time_range: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> DecisionDistributionResponse:
    start_dt, end_dt = parse_time_range(time_range, start_time, end_time)

    filters = []
    if start_dt:
        filters.append(DecisionRecord.created_at >= start_dt)
    if end_dt:
        filters.append(DecisionRecord.created_at <= end_dt)

    stats = (
        db.query(
            func.count(DecisionRecord.id).label("total"),
            func.sum(case((DecisionRecord.decision == "SUPPRESS", 1), else_=0)).label("suppressed"),
            func.sum(case((DecisionRecord.decision == "NOTIFY", 1), else_=0)).label("notified"),
            func.sum(case((DecisionRecord.decision == "ESCALATE", 1), else_=0)).label("escalated")
        )
        .filter(*filters)
        .first()
    )

    return DecisionDistributionResponse(
        suppressed=int(stats.suppressed or 0),
        notified=int(stats.notified or 0),
        escalated=int(stats.escalated or 0),
        total=int(stats.total or 0)
    )
