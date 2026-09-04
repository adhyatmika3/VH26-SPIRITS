from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
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
from app.services import analytics_service
from app.core.logging import logger

router = APIRouter(tags=["Analytics"])


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Get operational alert metrics overview",
    description="Returns aggregate counts, suppression rate, notification rate, escalation rate, and latency."
)
def get_analytics_overview(
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_analytics_overview(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching analytics overview: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch overview metrics")


@router.get(
    "/alerts-by-severity",
    response_model=List[SeverityDistributionItem],
    summary="Get alert volume distribution by severity",
    description="Returns counts and percentage breakdown grouped by severity level."
)
def get_alerts_by_severity(
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_alerts_by_severity(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching severity distribution: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch severity distribution")


@router.get(
    "/incidents-by-priority",
    response_model=List[IncidentPriorityDistributionItem],
    summary="Get incident volume distribution by priority / risk level",
    description="Returns counts and percentage breakdown of incidents grouped by priority (CRITICAL, HIGH, MEDIUM, LOW)."
)
def get_incidents_by_priority(
    time_range: Optional[str] = Query(None, description="Time window preset: 15m, 1h, 6h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_incidents_by_priority(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching incident priority distribution: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch incident priority distribution")


@router.get(
    "/alerts-by-source",
    response_model=List[SourceDistributionItem],
    summary="Get alert volume distribution by source",
    description="Returns counts and percentage breakdown grouped by monitoring source."
)
def get_alerts_by_source(
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_alerts_by_source(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching source distribution: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch source distribution")


@router.get(
    "/alerts-by-service",
    response_model=List[ServiceDistributionItem],
    summary="Get alert volume distribution by service",
    description="Returns counts and percentage breakdown grouped by service."
)
def get_alerts_by_service(
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_alerts_by_service(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching service distribution: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch service distribution")


@router.get(
    "/noisy-services",
    response_model=List[NoisyServiceItem],
    summary="Get top noisy services ranked by alert volume",
    description="Identifies the highest volume services with their suppression rates."
)
def get_noisy_services(
    limit: int = Query(10, ge=1, le=100, description="Max number of services to return"),
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_noisy_services(
            db=db,
            limit=limit,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching noisy services: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch noisy services")


@router.get(
    "/timeline",
    response_model=List[TimelinePoint],
    summary="Get time-series alert volume breakdown",
    description="Returns alert ingestion and decision volume bucketed by time interval."
)
def get_timeline(
    interval: str = Query("hour", pattern="^(minute|hour|day)$", description="Bucket interval: minute, hour, day"),
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_timeline(
            db=db,
            interval=interval,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching timeline analytics: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch timeline analytics")


@router.get(
    "/decisions",
    response_model=DecisionDistributionResponse,
    summary="Get counts of alert decisions",
    description="Returns total counts for suppressed, notified, and escalated decisions."
)
def get_decisions(
    time_range: Optional[str] = Query(None, description="Time window preset: 1h, 24h, 7d, 30d"),
    start_time: Optional[datetime] = Query(None, description="Explicit start UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Explicit end UTC timestamp"),
    db: Session = Depends(get_db)
):
    try:
        return analytics_service.get_decisions_distribution(
            db=db,
            time_range=time_range,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as exc:
        logger.error(f"Error fetching decision distribution: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch decision distribution")
