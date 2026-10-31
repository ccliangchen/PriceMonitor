from fastapi import APIRouter, Depends

from app.api.routes_accounts import router as accounts_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_listings import router as listings_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_products import router as products_router
from app.api.routes_settings import router as settings_router
from app.core.security import require_token

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])
api_router.include_router(health_router)
api_router.include_router(settings_router)
api_router.include_router(accounts_router)
api_router.include_router(listings_router)
api_router.include_router(products_router)
api_router.include_router(jobs_router)
api_router.include_router(notifications_router)
