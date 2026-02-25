from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from sqlalchemy.orm import Session


class ProviderError(Exception):
    """Raised when a provider request fails in a controlled way."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        meta: dict[str, Any] | None = None,
        endpoint: str | None = None,
        method: str = "GET",
        duration_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.meta = meta
        self.endpoint = endpoint
        self.method = method
        self.duration_ms = duration_ms


@dataclass(frozen=True)
class ProviderListing:
    provider: str
    external_id: str
    url: str
    title: str
    price: float
    currency: str = "USD"
    condition: str | None = None
    seller: str | None = None
    location: str | None = None
    discogs_release_id: int | None = None
    discogs_master_id: int | None = None
    raw: dict[str, Any] | None = None


class ProviderPaginationModel(str, Enum):
    OFFSET = "offset"
    CURSOR = "cursor"
    NONE = "none"


@dataclass(frozen=True)
class ProviderCapabilityContract:
    """Describes what feature surface a provider implementation supports."""

    supports_search: bool
    requires_auth: bool
    rate_limits_documented: bool
    listing_completeness: str
    pagination_model: ProviderPaginationModel


class ProviderClient(Protocol):
    """
    Provider client interface.
    Anything that implements this can be plugged into the runner.
    """

    name: str
    default_endpoint: str
    capability_contract: ProviderCapabilityContract

    def search(
        self, *, query: dict[str, Any], limit: int = 20, db: Session | None = None
    ) -> list[ProviderListing]:
        """
        Perform a search against the provider using the rule query blob.
        Should return a list of normalized ProviderListing objects.
        Raise ProviderError on failures you want the caller to handle.
        """
        raise NotImplementedError
