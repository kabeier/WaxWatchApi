from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "enc:v1"


@dataclass(frozen=True)
class DecryptResult:
    plaintext: str | None
    requires_migration: bool = False


class TokenCrypto:
    def __init__(self, *, key_id: str, fernet_key: str) -> None:
        self.key_id = key_id
        self._fernet = Fernet(fernet_key.encode("utf-8"))

    @classmethod
    def from_settings(cls, cfg: object) -> TokenCrypto:
        local_key = (getattr(cfg, "token_crypto_local_key", None) or "").strip()
        key_path = (getattr(cfg, "token_crypto_local_key_path", None) or "").strip()
        if not local_key and key_path:
            local_key = Path(key_path).read_text(encoding="utf-8").strip()
        if not local_key:
            raise RuntimeError("token crypto key material is not configured")

        key_id = (getattr(cfg, "token_crypto_kms_key_id", None) or "").strip() or "local-dev"
        return cls(key_id=key_id, fernet_key=local_key)

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value and value.startswith(f"{ENC_PREFIX}:"))

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        if self.is_encrypted(plaintext):
            return plaintext

        ciphertext = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{ENC_PREFIX}:{self.key_id}:{ciphertext}"

    def decrypt(self, stored_value: str | None) -> DecryptResult:
        if stored_value is None:
            return DecryptResult(plaintext=None)
        if not self.is_encrypted(stored_value):
            return DecryptResult(plaintext=stored_value, requires_migration=True)

        try:
            _, _, _key_id, ciphertext = stored_value.split(":", 3)
        except ValueError as exc:
            raise ValueError("malformed encrypted token envelope") from exc

        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("unable to decrypt token envelope") from exc

        return DecryptResult(plaintext=plaintext)
