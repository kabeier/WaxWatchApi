from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class EmailDeliveryRequest:
    to_address: str
    subject: str
    text_body: str
    html_body: str | None = None


@dataclass(frozen=True)
class EmailDeliveryResult:
    success: bool
    retryable: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class EmailProvider(Protocol):
    def send_email(self, request: EmailDeliveryRequest) -> EmailDeliveryResult: ...


class LocalStubEmailProvider:
    """Local/dev provider that doesn't call external services."""

    def send_email(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        logger.info(
            "notifications.email.stub.sent",
            extra={"to_address": request.to_address, "subject": request.subject},
        )
        return EmailDeliveryResult(success=True, retryable=False, provider_message_id="stub-local-delivery")


class SesEmailProvider:
    def __init__(self) -> None:
        try:
            import boto3
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime deps
            raise RuntimeError("boto3 is required when notification_email_provider=ses") from exc

        client_kwargs: dict[str, str] = {"region_name": settings.ses_region}
        if settings.ses_endpoint_url:
            client_kwargs["endpoint_url"] = settings.ses_endpoint_url
        self._client: Any = boto3.client("ses", **client_kwargs)

    def send_email(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        destination: dict[str, list[str]] = {"ToAddresses": [request.to_address]}
        provider_message: dict[str, Any] = {
            "Subject": {"Charset": "UTF-8", "Data": request.subject},
            "Body": {"Text": {"Charset": "UTF-8", "Data": request.text_body}},
        }
        if request.html_body:
            provider_message["Body"]["Html"] = {"Charset": "UTF-8", "Data": request.html_body}

        ses_payload: dict[str, Any] = {
            "Source": settings.ses_sender_email,
            "Destination": destination,
            "Message": provider_message,
        }
        if settings.ses_configuration_set:
            ses_payload["ConfigurationSetName"] = settings.ses_configuration_set

        try:
            response: dict[str, Any] = self._client.send_email(**ses_payload)
        except Exception as exc:  # pragma: no cover - depends on boto client behavior
            response_meta = getattr(exc, "response", {})
            error = response_meta.get("Error", {}) if isinstance(response_meta, dict) else {}
            code = error.get("Code") if isinstance(error, dict) else None
            error_message = error.get("Message") if isinstance(error, dict) else None
            retryable_codes = {"Throttling", "ServiceUnavailable", "RequestTimeout"}
            return EmailDeliveryResult(
                success=False,
                retryable=code in retryable_codes,
                error_code=code if isinstance(code, str) else None,
                error_message=(str(error_message) if error_message else str(exc)),
            )

        message_id = response.get("MessageId")
        return EmailDeliveryResult(
            success=True,
            retryable=False,
            provider_message_id=str(message_id) if message_id is not None else None,
        )


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    provider_name = settings.notification_email_provider.lower().strip()
    if provider_name == "ses":
        return SesEmailProvider()
    return LocalStubEmailProvider()
