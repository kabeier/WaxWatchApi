from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.logging import get_logger
from app.schemas.watch_rules import WatchRuleCreate, WatchRuleOut, WatchRuleUpdate
from app.services import watch_rules as service
from app.services.background import backfill_rule_matches_task

logger = get_logger(__name__)
router = APIRouter(prefix="/watch-rules", tags=["watch-rules"])


def _safe_sources(payload_query: dict | None) -> list[str] | None:
    if not isinstance(payload_query, dict):
        return None
    sources = payload_query.get("sources")
    if not isinstance(sources, list):
        return None
    return [str(s).strip().lower() for s in sources if str(s).strip()]


@router.post("", response_model=WatchRuleOut, status_code=201)
def create_rule(
    request: Request,
    payload: WatchRuleCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        rule = service.create_watch_rule(
            db,
            user_id=user_id,
            name=payload.name,
            query=payload.query,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
    except ValueError as e:
        logger.info(
            "watch_rules.create.validation_error",
            extra={"request_id": request_id, "user_id": str(user_id), "error": str(e)[:500]},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.create.db_error",
            extra={"request_id": request_id, "user_id": str(user_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    background_tasks.add_task(backfill_rule_matches_task, user_id, rule.id)

    logger.info(
        "watch_rules.create.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "rule_id": str(rule.id),
            "poll_interval_seconds": payload.poll_interval_seconds,
            "sources": _safe_sources(payload.query),
            "backfill_queued": True,
        },
    )
    return rule


@router.get("/{rule_id}", response_model=WatchRuleOut)
def get_rule(
    request: Request,
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        return service.get_watch_rule(db, user_id=user_id, rule_id=rule_id)
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.get.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None
    except HTTPException as e:
        if e.status_code == 404:
            logger.info(
                "watch_rules.get.not_found",
                extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
            )
        raise


@router.patch("/{rule_id}", response_model=WatchRuleOut)
def patch_rule(
    request: Request,
    rule_id: UUID,
    payload: WatchRuleUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        updated = service.update_watch_rule(
            db,
            user_id=user_id,
            rule_id=rule_id,
            name=payload.name,
            query=payload.query,
            is_active=payload.is_active,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        event = "watch_rules.patch.not_found" if status == 404 else "watch_rules.patch.validation_error"
        logger.info(
            event,
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "rule_id": str(rule_id),
                "error": msg[:500],
            },
        )
        raise HTTPException(status_code=status, detail=msg) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.patch.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.patch.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "rule_id": str(rule_id),
            "has_name": payload.name is not None,
            "has_query": payload.query is not None,
            "has_is_active": payload.is_active is not None,
            "has_poll_interval": payload.poll_interval_seconds is not None,
            "sources": _safe_sources(payload.query) if payload.query else None,
        },
    )
    return updated


@router.delete("/{rule_id}", response_model=WatchRuleOut)
def disable_rule(
    request: Request,
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")

    try:
        updated = service.disable_watch_rule(db, user_id=user_id, rule_id=rule_id)
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        event = "watch_rules.disable.not_found" if status == 404 else "watch_rules.disable.validation_error"
        logger.info(
            event,
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "rule_id": str(rule_id),
                "error": msg[:500],
            },
        )
        raise HTTPException(status_code=status, detail=msg) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.disable.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.disable.success",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )
    return updated
