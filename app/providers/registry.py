from __future__ import annotations

import os

from app.providers.discogs import DiscogsClient
from app.providers.mock import MockDiscogsClient, MockProvider

PROVIDERS: dict[str, type] = {
    "discogs": DiscogsClient,
    "mock": MockProvider,
}


def get_provider_class(name: str):
    """
    Central place to pick which provider class to use.

    In tests (ENVIRONMENT=test), we automatically swap Discogs -> MockDiscogsClient
    so CI is deterministic and offline.

    You can also force this with PROVIDER_FORCE_MOCK=1 in any environment.
    """
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("Provider name is required")

    env = (os.getenv("ENVIRONMENT") or "dev").lower()
    force_mock = (os.getenv("PROVIDER_FORCE_MOCK") or "").strip().lower() in {"1", "true", "yes"}

    if key == "discogs" and (env == "test" or force_mock):
        return MockDiscogsClient

    cls = PROVIDERS.get(key)
    if not cls:
        raise ValueError(f"Unknown provider: {key}")
    return cls
