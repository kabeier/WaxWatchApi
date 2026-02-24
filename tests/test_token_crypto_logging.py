from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, redact_sensitive_data
from app.core.token_crypto import TokenCrypto
from app.schemas.discogs import DiscogsConnectIn


class _Cfg:
    environment = "test"
    token_crypto_kms_key_id = "kms/test-key"
    token_crypto_local_key_path = None
    token_crypto_local_key = "5pq6kEUS_UIk1_4qatN-Lx42s3e362VNq5CgyI4LAZU="


def test_token_crypto_round_trip() -> None:
    crypto = TokenCrypto.from_settings(_Cfg())

    encrypted = crypto.encrypt("oauth-token")
    assert encrypted is not None
    assert encrypted.startswith("enc:v1:kms/test-key:")

    decrypted = crypto.decrypt(encrypted)
    assert decrypted.plaintext == "oauth-token"
    assert decrypted.requires_migration is False


def test_token_crypto_plaintext_marks_migration() -> None:
    crypto = TokenCrypto.from_settings(_Cfg())

    decrypted = crypto.decrypt("legacy-token")
    assert decrypted.plaintext == "legacy-token"
    assert decrypted.requires_migration is True


def test_log_redaction_never_emits_raw_token() -> None:
    logger = logging.getLogger("test.redaction")
    formatter = JsonFormatter()

    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        1,
        "oauth callback Authorization: Bearer secret-token",
        args=(),
        exc_info=None,
        extra={"access_token": "secret-token", "token": "secret-token"},
    )
    payload = json.loads(formatter.format(record))

    rendered = json.dumps(payload)
    assert "secret-token" not in rendered
    assert "***redacted***" in rendered


def test_discogs_connect_payload_serialization_redacts_access_token() -> None:
    payload = DiscogsConnectIn(external_user_id="user", access_token="my-token")

    dumped = payload.model_dump()
    dumped_json = payload.model_dump_json()

    assert dumped["access_token"] == "***redacted***"
    assert "my-token" not in dumped_json
    assert redact_sensitive_data({"token": "my-token"})["token"] == "***redacted***"
