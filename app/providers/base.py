from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


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
    raw: dict[str, Any] | None = None


class ProviderClient(Protocol):
    """
    Provider client interface.
    Anything that implements this can be plugged into the runner.
    """
    name: str

    def search(self, *, query: dict[str, Any], limit: int = 20) -> list[ProviderListing]:
        """
        Perform a search against the provider using the rule query blob.
        Should return a list of normalized ProviderListing objects.
        Raise ProviderError on failures you want the caller to handle.
        """
        raise NotImplementedError