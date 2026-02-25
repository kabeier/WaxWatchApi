from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# -------------------------
# Enums
# -------------------------


class Provider(str, enum.Enum):
    discogs = "discogs"
    ebay = "ebay"
    mock = "mock"
    musicbrainz = "musicbrainz"
    spotify = "spotify"


class ListingStatus(str, enum.Enum):
    active = "active"
    ended = "ended"  # sold/removed/expired
    unknown = "unknown"


class EventType(str, enum.Enum):
    # rule / watch lifecycle
    RULE_CREATED = "RULE_CREATED"
    RULE_UPDATED = "RULE_UPDATED"
    RULE_DISABLED = "RULE_DISABLED"
    RULE_DELETED = "RULE_DELETED"
    RULE_ENABLED = "RULE_ENABLED"

    WATCH_RELEASE_CREATED = "WATCH_RELEASE_CREATED"
    WATCH_RELEASE_UPDATED = "WATCH_RELEASE_UPDATED"
    WATCH_RELEASE_DISABLED = "WATCH_RELEASE_DISABLED"
    WATCH_RELEASE_ENABLED = "WATCH_RELEASE_ENABLED"

    # marketplace/listing changes
    LISTING_FIRST_SEEN = "LISTING_FIRST_SEEN"
    LISTING_PRICE_DROP = "LISTING_PRICE_DROP"
    LISTING_PRICE_RISE = "LISTING_PRICE_RISE"
    LISTING_ENDED = "LISTING_ENDED"

    # matches / alerts
    NEW_MATCH = "NEW_MATCH"

    # imports
    IMPORT_STARTED = "IMPORT_STARTED"
    IMPORT_COMPLETED = "IMPORT_COMPLETED"
    IMPORT_FAILED = "IMPORT_FAILED"


class NotificationChannel(str, enum.Enum):
    email = "email"
    realtime = "realtime"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


PROVIDER_ENUM = Enum(Provider, name="provider_enum", create_constraint=False)
LISTING_STATUS_ENUM = Enum(ListingStatus, name="listing_status_enum", create_constraint=False)
EVENT_TYPE_ENUM = Enum(EventType, name="event_type_enum", create_constraint=False)
NOTIFICATION_CHANNEL_ENUM = Enum(
    NotificationChannel,
    name="notification_channel_enum",
    create_constraint=False,
)
NOTIFICATION_STATUS_ENUM = Enum(
    NotificationStatus,
    name="notification_status_enum",
    create_constraint=False,
)

# -------------------------
# Tables
# -------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    watch_releases: Mapped[list[WatchRelease]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    watch_search_rules: Mapped[list[WatchSearchRule]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(back_populates="user", cascade="all, delete-orphan")
    external_account_links: Mapped[list[ExternalAccountLink]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    import_jobs: Mapped[list[ImportJob]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[UserNotificationPreference | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    provider_requests: Mapped[list[ProviderRequest]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ExternalAccountLink(Base):
    __tablename__ = "external_account_links"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_external_account_links_user_provider"),
        Index("ix_external_account_links_provider_external_user", "provider", "external_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    provider: Mapped[Provider] = mapped_column(PROVIDER_ENUM, nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text)
    token_metadata: Mapped[dict | None] = mapped_column(JSONB)

    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="external_account_links")
    import_jobs: Mapped[list[ImportJob]] = relationship(
        back_populates="external_account_link", cascade="all, delete-orphan"
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_user_created", "user_id", "created_at"),
        Index("ix_import_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    external_account_link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_account_links.id", ondelete="SET NULL")
    )

    provider: Mapped[Provider] = mapped_column(PROVIDER_ENUM, nullable=False)
    import_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    cursor: Mapped[str | None] = mapped_column(String(255))
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict] | None] = mapped_column(JSONB)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="import_jobs")
    external_account_link: Mapped[ExternalAccountLink | None] = relationship(back_populates="import_jobs")


class WatchRelease(Base):
    """
    Tracks a specific release (Discogs Release ID is the anchor).
    Optionally stores target price and condition preference.
    """

    __tablename__ = "watch_releases"
    __table_args__ = (
        UniqueConstraint("user_id", "discogs_release_id", name="uq_watch_release_user_release"),
        Index("ix_watch_releases_user_active", "user_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    discogs_release_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)  # cached display title
    artist: Mapped[str | None] = mapped_column(String(200))
    year: Mapped[int | None] = mapped_column(Integer)

    target_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    min_condition: Mapped[str | None] = mapped_column(String(30))  # keep as string for v1; normalize later
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="watch_releases")


class WatchSearchRule(Base):
    """
    Saved search / alert rule.
    It's intentionally generic: store a normalized JSON query + a display name.
    """

    __tablename__ = "watch_search_rules"
    __table_args__ = (
        Index("ix_watch_search_rules_user_active", "user_id", "is_active"),
        Index("ix_watch_search_rules_query_gin", "query", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Example:
    # {
    #   "keywords": ["primus", "vinyl"],
    #   "max_price": 120,
    #   "min_condition": "VG+",
    #   "sources": ["discogs","ebay"]
    # }
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # scheduling knobs
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="watch_search_rules")
    matches: Mapped[list[WatchMatch]] = relationship(back_populates="rule", cascade="all, delete-orphan")


class Listing(Base):
    """
    Normalized marketplace listing
    Uniqueness is provider + external_id.
    """

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_listing_provider_external"),
        Index("ix_listings_provider_status_last_seen", "provider", "status", "last_seen_at"),
        Index(
            "ix_listings_normalized_title_trgm",
            "normalized_title",
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
            postgresql_where=text("normalized_title IS NOT NULL"),
        ),
        CheckConstraint("price >= 0", name="ck_listings_price_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider: Mapped[Provider] = mapped_column(PROVIDER_ENUM, nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)

    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(Text)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    condition: Mapped[str | None] = mapped_column(String(30))
    seller: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(120))

    status: Mapped[ListingStatus] = mapped_column(
        LISTING_STATUS_ENUM, nullable=False, default=ListingStatus.active
    )

    # If you can infer it, store.
    discogs_release_id: Mapped[int | None] = mapped_column(Integer, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    raw: Mapped[dict | None] = mapped_column(JSONB)  # store raw provider payload (handy for debugging)

    price_snapshots: Mapped[list[PriceSnapshot]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    matches: Mapped[list[WatchMatch]] = relationship(back_populates="listing", cascade="all, delete-orphan")


class WatchMatch(Base):
    """
    Join table between a WatchSearchRule and a Listing.
    Unique per (rule_id, listing_id) so we don't alert twice for the same match.
    """

    __tablename__ = "watch_matches"
    __table_args__ = (
        UniqueConstraint("rule_id", "listing_id", name="uq_match_rule_listing"),
        Index("ix_watch_matches_rule_matched_at", "rule_id", "matched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_search_rules.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )

    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # optionally store "why it matched" (which filters passed)
    match_context: Mapped[dict | None] = mapped_column(JSONB)

    rule: Mapped[WatchSearchRule] = relationship(back_populates="matches")
    listing: Mapped[Listing] = relationship(back_populates="matches")


class Event(Base):
    """
    Durable event log.
    Used to:
    - power the UI activity feed
    - publish websocket notifications
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_created_at", "user_id", "created_at"),
        Index("ix_events_type_created_at", "type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    type: Mapped[EventType] = mapped_column(EVENT_TYPE_ENUM, nullable=False)

    watch_release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("watch_releases.id", ondelete="SET NULL")
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("watch_search_rules.id", ondelete="SET NULL")
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"))

    # Event payload (safe subset for UI)
    payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="events")
    notifications: Mapped[list[Notification]] = relationship(back_populates="event")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("event_id", "channel", name="uq_notifications_event_channel"),
        Index("ix_notifications_user_created_at", "user_id", "created_at"),
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(EVENT_TYPE_ENUM, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(NOTIFICATION_CHANNEL_ENUM, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        NOTIFICATION_STATUS_ENUM, nullable=False, default=NotificationStatus.pending
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="notifications")
    event: Mapped[Event] = relationship(back_populates="notifications")


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preferences"
    __table_args__ = (Index("ix_user_notification_preferences_user", "user_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    realtime_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_hours_start: Mapped[int | None] = mapped_column(Integer)
    quiet_hours_end: Mapped[int | None] = mapped_column(Integer)
    event_toggles: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="notification_preferences")


class PriceSnapshot(Base):
    """
    Time-series price history.
    Create one per polling observation (or only when price changes, your call).
    """

    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index("ix_price_snapshots_listing_recorded_at", "listing_id", "recorded_at"),
        CheckConstraint("price >= 0", name="ck_price_snapshots_price_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )

    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    listing: Mapped[Listing] = relationship(back_populates="price_snapshots")


class ProviderRequest(Base):
    """
    Observability: store provider call outcomes for debugging/rate limits.
    """

    __tablename__ = "provider_requests"
    __table_args__ = (
        Index("ix_provider_requests_user_created_at", "user_id", "created_at"),
        Index("ix_provider_requests_user_provider_created_at", "user_id", "provider", "created_at"),
        Index("ix_provider_requests_provider_created_at", "provider", "created_at"),
        Index("ix_provider_requests_status_code", "status_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[Provider] = mapped_column(PROVIDER_ENUM, nullable=False)

    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default="GET")
    status_code: Mapped[int | None] = mapped_column(Integer)

    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONB)  # e.g., rate-limit headers

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="provider_requests")
