import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.resolution_knowledge import ResolutionKnowledge
from app.services.ai_resolution_service import (
    generate_resolution,
    generate_resolution_sync,
    AIResolutionPayload
)

logger = logging.getLogger(__name__)

# Concurrency locking for anti-throttling & deduplicating AI requests per alert fingerprint
_sync_locks: Dict[str, threading.Lock] = {}
_sync_meta_lock = threading.Lock()

_async_locks: Dict[str, asyncio.Lock] = {}
_async_meta_lock = asyncio.Lock()


def get_sync_fingerprint_lock(fingerprint: str) -> threading.Lock:
    with _sync_meta_lock:
        if fingerprint not in _sync_locks:
            _sync_locks[fingerprint] = threading.Lock()
        return _sync_locks[fingerprint]


async def get_async_fingerprint_lock(fingerprint: str) -> asyncio.Lock:
    async with _async_meta_lock:
        if fingerprint not in _async_locks:
            _async_locks[fingerprint] = asyncio.Lock()
        return _async_locks[fingerprint]


@dataclass
class ResolutionResult:
    status: str  # "KNOWN", "RESOLVED", "ANALYSIS_PENDING", "FAILED"
    source: Optional[str]  # "knowledge_base", "automated_analysis", None
    probable_cause: Optional[str] = None
    resolution_steps: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    fingerprint: Optional[str] = None
    ai_called: bool = False
    knowledge_id: Optional[uuid.UUID] = None


def lookup_resolution(db: Session, fingerprint: str) -> Optional[ResolutionKnowledge]:
    """
    Queries stored ResolutionKnowledge by fingerprint.
    """
    stmt = select(ResolutionKnowledge).where(ResolutionKnowledge.fingerprint == fingerprint)
    return db.execute(stmt).scalars().first()


def resolve_unknown_alert_sync(
    db: Session,
    fingerprint: str,
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> ResolutionResult:
    """
    Synchronous resolution workflow with double-checked concurrency locking:
    1. First check: Fast DB lookup (no lock). If found, return immediately (source='knowledge_base').
    2. Acquire fingerprint-specific lock.
    3. Second check: Re-query DB inside lock.
    4. If still unknown: Query Google Gemini via Cloud AI.
    5. If AI responds: Persist to DB with unique constraint catch and return (source='automated_analysis').
    6. If AI fails/unavailable: Return ANALYSIS_PENDING / FAILED without crashing.
    """
    # Acquire concurrency lock for this fingerprint
    fp_lock = get_sync_fingerprint_lock(fingerprint)
    with fp_lock:
        existing = lookup_resolution(db, fingerprint)
        if existing:
            logger.debug("Resolution cache HIT for fingerprint %s (source=%s)", fingerprint[:8], existing.source)
            return ResolutionResult(
                status="KNOWN",
                source="knowledge_base",
                probable_cause=existing.probable_cause,
                resolution_steps=existing.resolution_steps or [],
                confidence=existing.confidence,
                fingerprint=fingerprint,
                ai_called=False,
                knowledge_id=existing.id
            )

        # 4. First occurrence of unknown alert -> Call AI service
        ai_payload = generate_resolution_sync(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )

        if not ai_payload:
            logger.info("AI resolution could not be generated for %s (%s). Marking ANALYSIS_PENDING.", alert_type, service)
            return ResolutionResult(
                status="ANALYSIS_PENDING",
                source=None,
                probable_cause=None,
                resolution_steps=[],
                confidence=None,
                fingerprint=fingerprint,
                ai_called=True
            )

        # 5. Persist to PostgreSQL
        now = datetime.now(timezone.utc)
        knowledge = ResolutionKnowledge(
            fingerprint=fingerprint,
            alert_type=alert_type,
            service=service,
            environment=environment,
            probable_cause=ai_payload.probable_cause,
            resolution_steps=ai_payload.resolution,
            confidence=ai_payload.confidence,
            source="automated_analysis",
            created_at=now,
            updated_at=now
        )

        try:
            db.add(knowledge)
            db.flush()
            logger.info("Persisted new automated resolution for fingerprint %s", fingerprint[:8])
            return ResolutionResult(
                status="RESOLVED",
                source="automated_analysis",
                probable_cause=knowledge.probable_cause,
                resolution_steps=knowledge.resolution_steps,
                confidence=knowledge.confidence,
                fingerprint=fingerprint,
                ai_called=True,
                knowledge_id=knowledge.id
            )
        except IntegrityError:
            db.rollback()
            # In case of database race condition, retrieve winning record
            existing = lookup_resolution(db, fingerprint)
            if existing:
                return ResolutionResult(
                    status="KNOWN",
                    source="knowledge_base",
                    probable_cause=existing.probable_cause,
                    resolution_steps=existing.resolution_steps or [],
                    confidence=existing.confidence,
                    fingerprint=fingerprint,
                    ai_called=True,
                    knowledge_id=existing.id
                )
            return ResolutionResult(
                status="ANALYSIS_PENDING",
                source=None,
                fingerprint=fingerprint,
                ai_called=True
            )


async def resolve_unknown_alert_async(
    db: Session,
    fingerprint: str,
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> ResolutionResult:
    """
    Asynchronous version of resolution workflow with double-checked concurrency locking.
    """
    # 1. Fast path: Check DB
    existing = lookup_resolution(db, fingerprint)
    if existing:
        return ResolutionResult(
            status="KNOWN",
            source="knowledge_base",
            probable_cause=existing.probable_cause,
            resolution_steps=existing.resolution_steps or [],
            confidence=existing.confidence,
            fingerprint=fingerprint,
            ai_called=False,
            knowledge_id=existing.id
        )

    # 2. Acquire async lock
    fp_lock = await get_async_fingerprint_lock(fingerprint)
    async with fp_lock:
        # 3. Double-check inside lock
        existing = lookup_resolution(db, fingerprint)
        if existing:
            return ResolutionResult(
                status="KNOWN",
                source="knowledge_base",
                probable_cause=existing.probable_cause,
                resolution_steps=existing.resolution_steps or [],
                confidence=existing.confidence,
                fingerprint=fingerprint,
                ai_called=False,
                knowledge_id=existing.id
            )

        # 4. Call async AI service
        ai_payload = await generate_resolution(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )

        if not ai_payload:
            return ResolutionResult(
                status="ANALYSIS_PENDING",
                source=None,
                probable_cause=None,
                resolution_steps=[],
                confidence=None,
                fingerprint=fingerprint,
                ai_called=True
            )

        # 5. Persist
        now = datetime.now(timezone.utc)
        knowledge = ResolutionKnowledge(
            fingerprint=fingerprint,
            alert_type=alert_type,
            service=service,
            environment=environment,
            probable_cause=ai_payload.probable_cause,
            resolution_steps=ai_payload.resolution,
            confidence=ai_payload.confidence,
            source="automated_analysis",
            created_at=now,
            updated_at=now
        )

        try:
            db.add(knowledge)
            db.flush()
            return ResolutionResult(
                status="RESOLVED",
                source="automated_analysis",
                probable_cause=knowledge.probable_cause,
                resolution_steps=knowledge.resolution_steps,
                confidence=knowledge.confidence,
                fingerprint=fingerprint,
                ai_called=True,
                knowledge_id=knowledge.id
            )
        except IntegrityError:
            db.rollback()
            existing = lookup_resolution(db, fingerprint)
            if existing:
                return ResolutionResult(
                    status="KNOWN",
                    source="knowledge_base",
                    probable_cause=existing.probable_cause,
                    resolution_steps=existing.resolution_steps or [],
                    confidence=existing.confidence,
                    fingerprint=fingerprint,
                    ai_called=True,
                    knowledge_id=existing.id
                )
            return ResolutionResult(
                status="ANALYSIS_PENDING",
                source=None,
                fingerprint=fingerprint,
                ai_called=True
            )


def get_resolution_for_incident(db: Session, incident_id: uuid.UUID) -> Optional[ResolutionResult]:
    """
    Finds resolution for a given incident by checking its associated canonical alerts.
    """
    incident = db.execute(select(Incident).where(Incident.id == incident_id)).scalars().first()
    if not incident:
        return None

    # Find canonical alerts for incident
    stmt = (
        select(CanonicalAlert)
        .where(CanonicalAlert.incident_id == incident_id)
        .order_by(CanonicalAlert.occurrence_count.desc(), CanonicalAlert.created_at.desc())
    )
    alerts = db.execute(stmt).scalars().all()

    for alert in alerts:
        knowledge = lookup_resolution(db, alert.fingerprint)
        if knowledge:
            return ResolutionResult(
                status="KNOWN",
                source=knowledge.source,
                probable_cause=knowledge.probable_cause,
                resolution_steps=knowledge.resolution_steps or [],
                confidence=knowledge.confidence,
                fingerprint=alert.fingerprint,
                ai_called=False,
                knowledge_id=knowledge.id
            )

    # If no resolution found yet, check if incident has any alert fingerprint
    first_alert = alerts[0] if alerts else None
    return ResolutionResult(
        status="ANALYSIS_PENDING" if incident.resolution_status != "RESOLVED" else "RESOLVED",
        source=None,
        probable_cause=None,
        resolution_steps=[],
        confidence=None,
        fingerprint=first_alert.fingerprint if first_alert else None,
        ai_called=False
    )
