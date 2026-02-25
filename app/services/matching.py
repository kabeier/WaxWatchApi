from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.metrics import record_listing_match_decision, record_listing_match_quality_proxy
from app.db import models

logger = get_logger(__name__)

_DEFAULT_CONFIDENCE_THRESHOLD = 0.82
_MIN_MARGIN = 0.10
_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "ep",
    "feat",
    "featuring",
    "ft",
    "lp",
    "mix",
    "record",
    "remaster",
    "stereo",
    "the",
    "vinyl",
}


@dataclass(frozen=True)
class ReleaseCandidate:
    discogs_release_id: int
    discogs_master_id: int | None
    title: str
    artist: str | None


@dataclass(frozen=True)
class CandidateScore:
    candidate: ReleaseCandidate
    confidence: float
    title_overlap: float
    artist_overlap: float


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()

    normalized = _TOKEN_RE.sub(" ", value.casefold())
    tokens = {token for token in normalized.split() if token and token not in _STOP_WORDS}
    return tokens


def _coverage_similarity(reference: set[str], observed: set[str]) -> float:
    if not reference or not observed:
        return 0.0
    intersection = len(reference.intersection(observed))
    return intersection / len(reference)


def _score_candidate(
    *,
    listing_title_tokens: set[str],
    listing_artist_tokens: set[str],
    candidate: ReleaseCandidate,
) -> CandidateScore:
    candidate_title_tokens = _tokenize(candidate.title)
    candidate_artist_tokens = _tokenize(candidate.artist)

    title_overlap = _coverage_similarity(candidate_title_tokens, listing_title_tokens)
    artist_overlap = _coverage_similarity(candidate_artist_tokens, listing_artist_tokens)

    # Give title much heavier weight than artist because many listings omit artist info.
    confidence = round((0.8 * title_overlap) + (0.2 * artist_overlap), 4)

    return CandidateScore(
        candidate=candidate,
        confidence=confidence,
        title_overlap=round(title_overlap, 4),
        artist_overlap=round(artist_overlap, 4),
    )


def _extract_listing_artist(raw: dict[str, Any] | None) -> str | None:
    if not isinstance(raw, dict):
        return None

    artist = raw.get("artist")
    if isinstance(artist, str) and artist.strip():
        return artist.strip()

    artists = raw.get("artists")
    if isinstance(artists, list) and artists:
        first = artists[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        if isinstance(first, str) and first.strip():
            return first.strip()

    return None


def normalize_title_tokens(title: str) -> list[str]:
    return sorted(_tokenize(title))


def score_release_candidates(
    *,
    listing_title: str,
    listing_artist: str | None,
    candidates: list[ReleaseCandidate],
) -> list[CandidateScore]:
    listing_title_tokens = _tokenize(listing_title)
    listing_artist_tokens = _tokenize(listing_artist)

    scores = [
        _score_candidate(
            listing_title_tokens=listing_title_tokens,
            listing_artist_tokens=listing_artist_tokens,
            candidate=candidate,
        )
        for candidate in candidates
    ]
    return sorted(scores, key=lambda score: score.confidence, reverse=True)


def _record_quality_proxy(*, matched: bool, confidence: float, margin: float) -> None:
    if matched:
        record_listing_match_quality_proxy(metric="predicted_positive")
        if margin < _MIN_MARGIN:
            record_listing_match_quality_proxy(metric="possible_false_positive")
    else:
        record_listing_match_quality_proxy(metric="predicted_negative")
        if confidence >= (_DEFAULT_CONFIDENCE_THRESHOLD * 0.7):
            record_listing_match_quality_proxy(metric="possible_false_negative")


def enrich_listing_mapping(
    db: Session,
    *,
    user_id: UUID,
    listing: models.Listing,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> bool:
    """
    Attempts to map listing -> Discogs release/master from user's watch releases.

    Returns True if the listing mapping was changed.
    """
    if listing.discogs_release_id is not None:
        record_listing_match_decision(outcome="already_mapped")
        return False

    candidates = [
        ReleaseCandidate(
            discogs_release_id=watch.discogs_release_id,
            discogs_master_id=watch.discogs_master_id,
            title=watch.title,
            artist=watch.artist,
        )
        for watch in db.query(models.WatchRelease)
        .filter(models.WatchRelease.user_id == user_id)
        .filter(models.WatchRelease.is_active.is_(True))
        .all()
    ]

    if not candidates:
        record_listing_match_decision(outcome="no_candidates")
        return False

    listing_artist = _extract_listing_artist(listing.raw)
    scores = score_release_candidates(
        listing_title=listing.title,
        listing_artist=listing_artist,
        candidates=candidates,
    )
    best = scores[0]
    second_confidence = scores[1].confidence if len(scores) > 1 else 0.0
    margin = round(best.confidence - second_confidence, 4)
    matched = best.confidence >= confidence_threshold and margin >= _MIN_MARGIN

    decision_payload = {
        "title_tokens": normalize_title_tokens(listing.title),
        "artist_tokens": normalize_title_tokens(listing_artist or ""),
        "top_candidate": {
            "discogs_release_id": best.candidate.discogs_release_id,
            "discogs_master_id": best.candidate.discogs_master_id,
            "confidence": best.confidence,
            "title_overlap": best.title_overlap,
            "artist_overlap": best.artist_overlap,
            "margin": margin,
        },
        "threshold": confidence_threshold,
        "matched": matched,
    }

    raw_payload = dict(listing.raw or {})
    raw_payload.setdefault("matching", {})
    raw_payload["matching"]["discogs_mapping"] = decision_payload

    if matched:
        listing.discogs_release_id = best.candidate.discogs_release_id
        listing.discogs_master_id = best.candidate.discogs_master_id
        record_listing_match_decision(outcome="mapped")
    else:
        record_listing_match_decision(outcome="below_threshold")

    _record_quality_proxy(matched=matched, confidence=best.confidence, margin=margin)

    listing.raw = raw_payload
    db.add(listing)
    db.flush()

    logger.info(
        "matching.discogs_mapping_decision",
        extra={
            "listing_id": str(listing.id),
            "user_id": str(user_id),
            "matched": matched,
            "confidence": best.confidence,
            "margin": margin,
            "discogs_release_id": best.candidate.discogs_release_id,
            "discogs_master_id": best.candidate.discogs_master_id,
        },
    )

    return matched


def enrich_unmapped_listings_for_user(
    db: Session,
    *,
    user_id: UUID,
    limit: int = 200,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> int:
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.discogs_release_id.is_(None))
        .order_by(models.Listing.last_seen_at.desc())
        .limit(limit)
        .all()
    )

    mapped = 0
    for listing in listings:
        if enrich_listing_mapping(
            db,
            user_id=user_id,
            listing=listing,
            confidence_threshold=confidence_threshold,
        ):
            mapped += 1
    return mapped
