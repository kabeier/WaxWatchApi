from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.yml"

# These values determine provider/auth enablement in production and must never
# use non-empty fallback defaults in committed compose files.
SENSITIVE_RUNTIME_VARS = {
    "DISCOGS_USER_AGENT",
    "DISCOGS_TOKEN",
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "AUTH_ISSUER",
    "AUTH_JWKS_URL",
    "TOKEN_CRYPTO_KMS_KEY_ID",
}

# Matches ${VAR:-fallback} and captures VAR/fallback.
FALLBACK_PATTERN = re.compile(r"\$\{([A-Z0-9_]+):-([^}]*)\}")


def main() -> int:
    compose_content = COMPOSE_FILE.read_text(encoding="utf-8")
    errors: list[str] = []

    for line_number, line in enumerate(compose_content.splitlines(), start=1):
        for match in FALLBACK_PATTERN.finditer(line):
            var_name, fallback = match.group(1), match.group(2)
            if var_name not in SENSITIVE_RUNTIME_VARS:
                continue
            if fallback.strip():
                errors.append(
                    f"{COMPOSE_FILE.relative_to(ROOT)}:{line_number} uses a non-empty fallback for {var_name}: {match.group(0)}"
                )

    if errors:
        print(
            "Fail-closed policy violation: sensitive runtime vars must not have fake fallback defaults in docker-compose.yml"
        )
        for error in errors:
            print(f" - {error}")
        return 1

    print("ok: docker-compose sensitive runtime vars are fail-closed (no non-empty fallback defaults)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
