from fastapi import APIRouter, Depends

from app.api.routes_health import router as health_router
from app.api.routes_settings import router as settings_router
from app.core.security import require_token

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])
api_router.include_router(health_router)
api_router.include_router(settings_router)
