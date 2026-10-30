import time

from fastapi import APIRouter, Request

from app import __version__
from app.core.db import check_db
from app.core.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    uptime_seconds = max(0, int(time.monotonic() - request.app.state.started_at))
    return HealthResponse(
        version=__version__,
        uptime_seconds=uptime_seconds,
        data_dir=str(settings.data_dir),
        database="ok" if check_db() else "error",
    )


@router.post("/shutdown")
def shutdown(request: Request) -> dict[str, bool]:
    server = getattr(request.app.state, "server", None)
    if server is not None:
        server.should_exit = True
    return {"ok": True}
