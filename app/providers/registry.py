from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings
from app.providers.base import ProviderCapabilityContract
from app.providers.discogs import DiscogsClient
from app.providers.ebay import EbayClient
from app.providers.mock import MockDiscogsClient, MockProvider


@dataclass(frozen=True)
class ProviderRegistration:
    name: str
    client_class: type
    capability_contract: ProviderCapabilityContract
    enabled: bool = True
    disabled_reason: str | None = None
    test_client_class: type | None = None


def _discogs_enabled() -> tuple[bool, str | None]:
    return settings.provider_enabled("discogs")


def _ebay_enabled() -> tuple[bool, str | None]:
    return settings.provider_enabled("ebay")


def _mock_enabled() -> tuple[bool, str | None]:
    configured, reason = settings.provider_enabled("mock")
    if not configured:
        return False, reason

    environment = (os.getenv("ENVIRONMENT") or settings.environment or "dev").strip().lower()
    if environment in {"dev", "test", "local"}:
        return True, None

    return False, f"mock provider disabled in environment '{environment}'"


def mock_provider_enabled() -> bool:
    return _mock_enabled()[0]


def _build_registrations() -> dict[str, ProviderRegistration]:
    providers: dict[str, ProviderRegistration] = {}

    def register_provider(
        *,
        name: str,
        client_class: type,
        capability_contract: ProviderCapabilityContract,
        test_client_class: type | None = None,
        enabled_check: Callable[[], tuple[bool, str | None]] | None = None,
    ) -> None:
        enabled, reason = enabled_check() if enabled_check else (True, None)
        providers[name] = ProviderRegistration(
            name=name,
            client_class=client_class,
            capability_contract=capability_contract,
            enabled=enabled,
            disabled_reason=reason,
            test_client_class=test_client_class,
        )

    register_provider(
        name="discogs",
        client_class=DiscogsClient,
        test_client_class=MockDiscogsClient,
        enabled_check=_discogs_enabled,
        capability_contract=DiscogsClient.capability_contract,
    )
    register_provider(
        name="ebay",
        client_class=EbayClient,
        enabled_check=_ebay_enabled,
        capability_contract=EbayClient.capability_contract,
    )
    register_provider(
        name="mock",
        client_class=MockProvider,
        enabled_check=_mock_enabled,
        capability_contract=MockProvider.capability_contract,
    )

    return providers


PROVIDERS: dict[str, ProviderRegistration] = _build_registrations()


def list_available_providers() -> list[str]:
    return [name for name, registration in PROVIDERS.items() if registration.enabled]


def get_provider_registration(name: str) -> ProviderRegistration:
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("Provider name is required")

    registration = PROVIDERS.get(key)
    if not registration:
        raise ValueError(f"Unknown provider: {key}")

    if not registration.enabled:
        reason = registration.disabled_reason or "provider configuration unavailable"
        raise ValueError(f"Provider '{key}' is disabled: {reason}")

    return registration


def get_provider_class(name: str):
    """
    Central place to pick which provider class to use.

    In tests (ENVIRONMENT=test), we can swap a provider to its test implementation.
    You can also force this with PROVIDER_FORCE_MOCK=1 in any environment.
    """
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("Provider name is required")

    registration = PROVIDERS.get(key)
    if not registration:
        raise ValueError(f"Unknown provider: {key}")

    env = (os.getenv("ENVIRONMENT") or "dev").lower()
    force_mock = (os.getenv("PROVIDER_FORCE_MOCK") or "").strip().lower() in {"1", "true", "yes"}

    if registration.test_client_class and (env == "test" or force_mock):
        return registration.test_client_class

    if not registration.enabled:
        reason = registration.disabled_reason or "provider configuration unavailable"
        raise ValueError(f"Provider '{key}' is disabled: {reason}")

    return registration.client_class
