from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.api.pagination import PaginationParams, apply_created_id_pagination, get_pagination_params
from app.db import models
from app.schemas.provider_requests import ProviderRequestOut, ProviderRequestSummaryOut

router = APIRouter(prefix="/provider-requests", tags=["provider-requests"])


@router.get("", response_model=list[ProviderRequestOut])
def list_provider_requests(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    rows = apply_created_id_pagination(
        db.query(models.ProviderRequest).filter(models.ProviderRequest.user_id == user_id),
        models.ProviderRequest,
        pagination,
    ).all()
    return rows


@router.get("/summary", response_model=list[ProviderRequestSummaryOut])
def provider_request_summary(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    rows = (
        db.query(
            models.ProviderRequest.provider.label("provider"),
            func.count(models.ProviderRequest.id).label("total_requests"),
            func.sum(case((models.ProviderRequest.status_code >= 400, 1), else_=0)).label("error_requests"),
            func.avg(models.ProviderRequest.duration_ms).label("avg_duration_ms"),
        )
        .filter(models.ProviderRequest.user_id == user_id)
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
