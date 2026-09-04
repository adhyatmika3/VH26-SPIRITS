import json
import urllib.parse
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.config import settings
from app.core.logging import logger
from app.services.slack_service import (
    check_slack_health,
    verify_slack_signature,
    handle_slack_interaction
)

router = APIRouter(prefix="/integrations/slack", tags=["Slack Integration"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Slack Integration Health Check",
    description="Returns configuration and connectivity status of Slack integration without exposing secrets."
)
def get_slack_health():
    """
    Returns health status of the Slack integration:
    - enabled: whether SLACK_ENABLED is True
    - configured: whether a valid bot token is provided
    - connected: whether test connection (auth.test) succeeds
    - channel: configured destination channel
    """
    return check_slack_health()


@router.post(
    "/interactions",
    status_code=status.HTTP_200_OK,
    summary="Slack Interactive Actions Endpoint",
    description="Handles Slack interactive button actions (Acknowledge, Resolve) with signature verification."
)
async def handle_interactions(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receives and processes interactive button clicks from Slack.
    Validates HMAC-SHA256 signature against SLACK_SIGNING_SECRET.
    Rejects unauthorized, replayed, or invalid requests.
    Routes action safely through the backend state model.
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    # 1. Signature Verification
    if settings.SLACK_SIGNING_SECRET:
        if not verify_slack_signature(body=raw_body, headers=headers):
            logger.warning("Rejected Slack interaction: Invalid signature or timestamp window exceeded.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Slack request signature or expired timestamp."
            )
    else:
        logger.warning("SLACK_SIGNING_SECRET is not configured; interaction verification rejected.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Slack integration signature verification secret not configured."
        )

    # 2. Parse Slack form-encoded payload
    try:
        content_type = headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            parsed = urllib.parse.parse_qs(raw_body.decode("utf-8"))
            if "payload" not in parsed:
                raise ValueError("Missing 'payload' field in url-encoded body.")
            payload = json.loads(parsed["payload"][0])
        elif "application/json" in content_type:
            payload = json.loads(raw_body.decode("utf-8"))
        else:
            # Fallback parsing
            parsed = urllib.parse.parse_qs(raw_body.decode("utf-8"))
            if "payload" in parsed:
                payload = json.loads(parsed["payload"][0])
            else:
                payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.error(f"Failed to parse Slack interaction payload: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed Slack interaction payload: {exc}"
        )

    # 3. Process action through state engine
    try:
        response_data = handle_slack_interaction(db=db, payload=payload)
        return response_data
    except Exception as exc:
        logger.error(f"Error handling Slack interaction: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process Slack action: {str(exc)}"
        )
