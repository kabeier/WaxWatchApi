from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models

router = APIRouter(prefix="/dev/provider-requests", tags=["dev"])


@router.get("")
def list_provider_requests(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    rows = (
        db.query(models.ProviderRequest)
        .order_by(models.ProviderRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "provider": r.provider.value,
            "endpoint": r.endpoint,
            "method": r.method,
            "status_code": r.status_code,
            "duration_ms": r.duration_ms,
            "error": r.error,
            "meta": r.meta,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]