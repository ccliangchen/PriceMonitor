from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import JobRun
from app.core.schemas import JobRunResponse

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/jobs", response_model=list[JobRunResponse])
def list_jobs(
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
) -> list[JobRunResponse]:
    rows = db.scalars(
        select(JobRun).order_by(JobRun.started_at.desc(), JobRun.id.desc()).limit(limit)
    ).all()
    return [JobRunResponse.model_validate(item) for item in rows]
