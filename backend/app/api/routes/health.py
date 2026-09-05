from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.slack_service import check_slack_health

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check distinguishing core application health from external dependencies.
    A Slack outage reports slack: 'degraded' but preserves application status: 'healthy'.
    """
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    slack_info = check_slack_health()
    slack_status = slack_info.get("status", "degraded")

    app_status = "healthy" if db_status == "healthy" else "degraded"

    return {
        "status": app_status,
        "database": db_status,
        "slack": slack_status
    }


@router.get("/health/db", status_code=status.HTTP_200_OK)
def db_health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
