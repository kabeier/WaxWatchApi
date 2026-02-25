from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

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
            import boto3  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime deps
            raise RuntimeError("boto3 is required when notification_email_provider=ses") from exc

        client_kwargs: dict[str, str] = {"region_name": settings.ses_region}
        if settings.ses_endpoint_url:
            client_kwargs["endpoint_url"] = settings.ses_endpoint_url
        self._client = boto3.client("ses", **client_kwargs)

    def send_email(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        destination = {"ToAddresses": [request.to_address]}
        message: dict[str, dict] = {
            "Subject": {"Charset": "UTF-8", "Data": request.subject},
            "Body": {"Text": {"Charset": "UTF-8", "Data": request.text_body}},
        }
        if request.html_body:
            message["Body"]["Html"] = {"Charset": "UTF-8", "Data": request.html_body}

        ses_payload = {
            "Source": settings.ses_sender_email,
            "Destination": destination,
            "Message": message,
        }
        if settings.ses_configuration_set:
            ses_payload["ConfigurationSetName"] = settings.ses_configuration_set

        try:
            response = self._client.send_email(**ses_payload)
        except Exception as exc:  # pragma: no cover - depends on boto client behavior
            response_meta = getattr(exc, "response", {})
            error = response_meta.get("Error", {}) if isinstance(response_meta, dict) else {}
            code = error.get("Code")
            message = error.get("Message") or str(exc)
            retryable_codes = {"Throttling", "ServiceUnavailable", "RequestTimeout"}
            return EmailDeliveryResult(
                success=False,
                retryable=code in retryable_codes,
                error_code=code,
                error_message=message,
            )

        return EmailDeliveryResult(
            success=True,
            retryable=False,
            provider_message_id=response.get("MessageId"),
        )


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    provider_name = settings.notification_email_provider.lower().strip()
    if provider_name == "ses":
        return SesEmailProvider()
    return LocalStubEmailProvider()
