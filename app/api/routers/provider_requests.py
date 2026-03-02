from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user_id, get_current_user_id, get_db
from app.api.pagination import PaginationParams, apply_created_id_pagination, get_pagination_params
from app.db import models
from app.schemas.provider_requests import (
    ProviderRequestAdminOut,
    ProviderRequestOut,
    ProviderRequestSummaryOut,
)

router = APIRouter(prefix="/provider-requests", tags=["provider-requests"])


_error_request_case = case(
    (
        or_(
            models.ProviderRequest.status_code >= 400,
            and_(models.ProviderRequest.error.is_not(None), models.ProviderRequest.error != ""),
        ),
        1,
    ),
    else_=0,
)


def _provider_to_string(provider: models.Provider | str) -> str:
    return provider.value if hasattr(provider, "value") else str(provider)


def _apply_admin_filters(
    query: SAQuery,
    *,
    provider: models.Provider | None,
    status_code_gte: int | None,
    status_code_lte: int | None,
    created_from: datetime | None,
    created_to: datetime | None,
    user_id: UUID | None,
) -> SAQuery:
    if status_code_gte is not None and status_code_lte is not None and status_code_gte > status_code_lte:
        raise HTTPException(status_code=422, detail="status_code_gte cannot be greater than status_code_lte")
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(status_code=422, detail="created_from cannot be greater than created_to")

    if provider is not None:
        query = query.filter(models.ProviderRequest.provider == provider)
    if status_code_gte is not None:
        query = query.filter(models.ProviderRequest.status_code >= status_code_gte)
    if status_code_lte is not None:
        query = query.filter(models.ProviderRequest.status_code <= status_code_lte)
    if created_from is not None:
        query = query.filter(models.ProviderRequest.created_at >= created_from)
    if created_to is not None:
        query = query.filter(models.ProviderRequest.created_at <= created_to)
    if user_id is not None:
        query = query.filter(models.ProviderRequest.user_id == user_id)

    return query


@router.get("", response_model=list[ProviderRequestOut])
def list_provider_requests(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    try:
        rows = apply_created_id_pagination(
            db.query(models.ProviderRequest).filter(models.ProviderRequest.user_id == user_id),
            models.ProviderRequest,
            pagination,
        ).all()
        return rows
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc


@router.get("/summary", response_model=list[ProviderRequestSummaryOut])
def provider_request_summary(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        rows = (
            db.query(
                models.ProviderRequest.provider.label("provider"),
                func.count(models.ProviderRequest.id).label("total_requests"),
                func.sum(_error_request_case).label("error_requests"),
                func.avg(models.ProviderRequest.duration_ms).label("avg_duration_ms"),
            )
            .filter(models.ProviderRequest.user_id == user_id)
            .group_by(models.ProviderRequest.provider)
            .order_by(models.ProviderRequest.provider.asc())
            .all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc

    return [
        ProviderRequestSummaryOut(
            provider=_provider_to_string(r.provider),
            total_requests=int(r.total_requests or 0),
            error_requests=int(r.error_requests or 0),
            avg_duration_ms=float(r.avg_duration_ms) if r.avg_duration_ms is not None else None,
        )
        for r in rows
    ]


@router.get("/admin", response_model=list[ProviderRequestAdminOut])
def list_provider_requests_admin(
    db: Session = Depends(get_db),
    _admin_user_id: UUID = Depends(get_current_admin_user_id),
    pagination: PaginationParams = Depends(get_pagination_params),
    provider: models.Provider | None = Query(default=None),
    status_code_gte: int | None = Query(default=None, ge=100, le=599),
    status_code_lte: int | None = Query(default=None, ge=100, le=599),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
):
    try:
        base_query = _apply_admin_filters(
            db.query(models.ProviderRequest),
            provider=provider,
            status_code_gte=status_code_gte,
            status_code_lte=status_code_lte,
            created_from=created_from,
            created_to=created_to,
            user_id=user_id,
        )
        return apply_created_id_pagination(base_query, models.ProviderRequest, pagination).all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc


@router.get("/admin/summary", response_model=list[ProviderRequestSummaryOut])
def provider_request_summary_admin(
    db: Session = Depends(get_db),
    _admin_user_id: UUID = Depends(get_current_admin_user_id),
    provider: models.Provider | None = Query(default=None),
    status_code_gte: int | None = Query(default=None, ge=100, le=599),
    status_code_lte: int | None = Query(default=None, ge=100, le=599),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
):
    try:
        base_query = _apply_admin_filters(
            db.query(
                models.ProviderRequest.provider.label("provider"),
                func.count(models.ProviderRequest.id).label("total_requests"),
                func.sum(_error_request_case).label("error_requests"),
                func.avg(models.ProviderRequest.duration_ms).label("avg_duration_ms"),
            ),
            provider=provider,
            status_code_gte=status_code_gte,
            status_code_lte=status_code_lte,
            created_from=created_from,
            created_to=created_to,
            user_id=user_id,
        )

        rows = (
            base_query.group_by(models.ProviderRequest.provider)
            .order_by(models.ProviderRequest.provider.asc())
            .all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="db error") from exc

    return [
        ProviderRequestSummaryOut(
            provider=_provider_to_string(r.provider),
            total_requests=int(r.total_requests or 0),
            error_requests=int(r.error_requests or 0),
            avg_duration_ms=float(r.avg_duration_ms) if r.avg_duration_ms is not None else None,
        )
        for r in rows
    ]
