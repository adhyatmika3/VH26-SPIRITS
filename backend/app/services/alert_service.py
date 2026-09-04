from sqlalchemy.orm import Session
from app.core.logging import logger
from app.models.raw_alert import RawAlert
from app.schemas.webhook import AlertWebhookPayload


def ingest_raw_alert(db: Session, payload: AlertWebhookPayload) -> RawAlert:
    """
    Phase 1: Persist the raw incoming alert into PostgreSQL.
    """
    raw_dict = payload.model_dump(mode="json")

    raw_alert = RawAlert(
        source=payload.source,
        alert_name=payload.alert_name,
        service=payload.service,
        resource=payload.resource,
        severity=payload.severity.lower(),
        status=payload.status.lower(),
        timestamp=payload.timestamp,
        labels=payload.labels,
        annotations=payload.annotations,
        raw_payload=raw_dict
    )

    db.add(raw_alert)
    db.commit()
    db.refresh(raw_alert)

    logger.info(
        f"Persisted RawAlert [id={raw_alert.id}, source={raw_alert.source}, "
        f"alert={raw_alert.alert_name}, service={raw_alert.service}]"
    )

    return raw_alert
