from __future__ import annotations

import argparse
import enum
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = ROOT / "docs" / "openapi.snapshot.json"
DEFAULT_DATABASE_URL = "postgresql+psycopg://snapshot:snapshot@localhost:5432/snapshot"
DEFAULT_TOKEN_CRYPTO_LOCAL_KEY = "5pq6kEUS_UIk1_4qatN-Lx42s3e362VNq5CgyI4LAZU="


def _ensure_str_enum_support() -> None:
    if hasattr(enum, "StrEnum"):
        return

    class _CompatStrEnum(str, enum.Enum):  # noqa: UP042
        pass

    enum.StrEnum = _CompatStrEnum  # type: ignore[misc,assignment]


def build_openapi_schema() -> dict[str, Any]:
    """Build the FastAPI OpenAPI schema from app/main.py with deterministic env defaults."""

    os.environ.setdefault("DATABASE_URL", DEFAULT_DATABASE_URL)
    os.environ.setdefault("ENVIRONMENT", "prod")
    os.environ.setdefault("TOKEN_CRYPTO_LOCAL_KEY", DEFAULT_TOKEN_CRYPTO_LOCAL_KEY)

    _ensure_str_enum_support()
    from app.main import app

    return app.openapi()


def render_deterministic_openapi_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def export_openapi_schema(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_deterministic_openapi_json(build_openapi_schema()),
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export deterministic OpenAPI JSON from app/main.py")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Output file path (default: docs/openapi.snapshot.json).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_path = Path(args.output)
    export_openapi_schema(output_path)
    print(f"OpenAPI schema exported: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
