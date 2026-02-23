from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.db import models
from app.schemas.provider_requests import ProviderRequestOut, ProviderRequestSummaryOut

router = APIRouter(prefix="/provider-requests", tags=["provider-requests"])


@router.get("", response_model=list[ProviderRequestOut])
def list_provider_requests(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    _ = user_id
    rows = (
        db.query(models.ProviderRequest)
        .order_by(models.ProviderRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.get("/summary", response_model=list[ProviderRequestSummaryOut])
def provider_request_summary(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    _ = user_id

    rows = (
        db.query(
            models.ProviderRequest.provider.label("provider"),
            func.count(models.ProviderRequest.id).label("total_requests"),
            func.sum(case((models.ProviderRequest.status_code >= 400, 1), else_=0)).label("error_requests"),
            func.avg(models.ProviderRequest.duration_ms).label("avg_duration_ms"),
        )
        .group_by(models.ProviderRequest.provider)
        .order_by(models.ProviderRequest.provider.asc())
        .all()
    )

    return [
        ProviderRequestSummaryOut(
            provider=r.provider.value if hasattr(r.provider, "value") else str(r.provider),
            total_requests=int(r.total_requests or 0),
            error_requests=int(r.error_requests or 0),
            avg_duration_ms=float(r.avg_duration_ms) if r.avg_duration_ms is not None else None,
        )
        for r in rows
    ]
