from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request, status
from app.services.load_test_service import (
    load_test_manager,
    LoadTestConfig,
    LoadTestStatusResponse
)

router = APIRouter(prefix="/load-test", tags=["Load Test & High Volume"])


@router.post(
    "/start",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Start interactive high-volume alert load test",
    description="Dispatches controlled bursts of alerts across concurrent worker dispatchers through the genuine webhook pipeline."
)
async def start_load_test(
    request: Request,
    config: LoadTestConfig
):
    if load_test_manager.status == "PROCESSING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A load test is already actively running. Please wait for it to complete or stop it first."
        )

    await load_test_manager.start(app=request.app, config=config)
    return {
        "status": "PROCESSING",
        "message": f"Load test started: {config.count} alerts at {config.rate}/sec across {config.concurrency} workers.",
        "config": config.model_dump()
    }


@router.post(
    "/stop",
    response_model=LoadTestStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Stop / Cancel active alert load test",
    description="Cancels active feeder and worker tasks cleanly, preserving all accepted alerts and querying PostgreSQL for downstream counts."
)
async def stop_load_test():
    await load_test_manager.stop()
    return load_test_manager.get_status()


@router.get(
    "/status",
    response_model=LoadTestStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get real-time operational load test status",
    description="Returns live counters for submitted, accepted, processed, backlog, worker count, rate, and verified PostgreSQL downstream results."
)
def get_load_test_status():
    return load_test_manager.get_status()


@router.get(
    "/metrics",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Get timeseries metrics for operational charts",
    description="Returns timeseries datapoints of incoming vs processed rates, latency, and backlog over the duration of the test."
)
def get_load_test_metrics():
    return load_test_manager.get_metrics_history()


@router.post(
    "/reset",
    response_model=Dict[str, str],
    status_code=status.HTTP_200_OK,
    summary="Reset load test metrics to IDLE",
    description="Resets the load test manager counters back to IDLE state. Cannot be invoked while a test is actively processing."
)
def reset_load_test():
    try:
        load_test_manager.reset()
        return {"status": "IDLE", "message": "Load test telemetry reset successfully."}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
