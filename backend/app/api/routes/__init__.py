from fastapi import APIRouter
from app.api.routes.health import router as health_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.decisions import router as decisions_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.escalations import router as escalations_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.dashboard import router as dashboard_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(metrics_router)  # /metrics
api_router.include_router(alerts_router, prefix="/api/v1")
api_router.include_router(incidents_router, prefix="/api/v1")
api_router.include_router(decisions_router, prefix="/api/v1")
api_router.include_router(notifications_router, prefix="/api/v1")
api_router.include_router(escalations_router, prefix="/api/v1")
api_router.include_router(analytics_router, prefix="/api/v1/analytics")
api_router.include_router(analytics_router, prefix="/api/analytics")
api_router.include_router(dashboard_router, prefix="/api/v1")
api_router.include_router(dashboard_router, prefix="/api")

