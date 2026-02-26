from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db, rate_limit_scope
from app.schemas.search import SaveSearchAlertRequest, SearchQuery, SearchResponse
from app.schemas.watch_rules import WatchRuleOut
from app.services import search as search_service

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(rate_limit_scope("search", require_authenticated_principal=True))],
)


@router.post("", response_model=SearchResponse)
def search_listings(
    payload: SearchQuery,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return search_service.run_search(db, user_id=user_id, query=payload)


@router.post("/save-alert", response_model=WatchRuleOut)
def save_alert(
    payload: SaveSearchAlertRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return search_service.save_search_alert(
        db,
        user_id=user_id,
        name=payload.name,
        query=payload.query,
        poll_interval_seconds=payload.poll_interval_seconds,
    )
