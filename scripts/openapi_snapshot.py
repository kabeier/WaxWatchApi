from __future__ import annotations

import argparse
import difflib
import enum
import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_PATH = ROOT / "docs" / "openapi.snapshot.json"


def _ensure_str_enum_support() -> None:
    if hasattr(enum, "StrEnum"):
        return

    class _CompatStrEnum(str, enum.Enum):
        pass

    enum.StrEnum = _CompatStrEnum


def _build_schema() -> dict[str, Any]:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://snapshot:snapshot@localhost:5432/snapshot")
    os.environ.setdefault("ENVIRONMENT", "prod")
    os.environ.setdefault("TOKEN_CRYPTO_LOCAL_KEY", Fernet.generate_key().decode("utf-8"))

    _ensure_str_enum_support()
    from app.main import app

    return app.openapi()


def _to_deterministic_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _classify_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    notes: list[str] = []

    old_paths = old.get("paths", {})
    new_paths = new.get("paths", {})

    removed_paths = sorted(set(old_paths) - set(new_paths))
    if removed_paths:
        notes.append(f"breaking: removed paths ({len(removed_paths)}): {', '.join(removed_paths[:5])}")

    removed_ops: list[str] = []
    for path in sorted(set(old_paths) & set(new_paths)):
        old_methods = {k.lower() for k in old_paths.get(path, {})}
        new_methods = {k.lower() for k in new_paths.get(path, {})}
        for method in sorted(old_methods - new_methods):
            removed_ops.append(f"{method.upper()} {path}")
    if removed_ops:
        notes.append(f"breaking: removed operations ({len(removed_ops)}): {', '.join(removed_ops[:5])}")

    added_paths = sorted(set(new_paths) - set(old_paths))
    if added_paths:
        notes.append(f"non-breaking: added paths ({len(added_paths)}): {', '.join(added_paths[:5])}")

    old_components = old.get("components", {}).get("schemas", {})
    new_components = new.get("components", {}).get("schemas", {})
    removed_schemas = sorted(set(old_components) - set(new_components))
    if removed_schemas:
        notes.append(
            f"breaking: removed component schemas ({len(removed_schemas)}): {', '.join(removed_schemas[:5])}"
        )

    if not notes:
        notes.append("schema changed; no clear breaking signature detected")

    return notes


def _print_diff(old_text: str, new_text: str) -> None:
    diff = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="docs/openapi.snapshot.json",
            tofile="generated-openapi-schema",
            lineterm="",
        )
    )
    max_lines = 200
    for line in diff[:max_lines]:
        print(line)
    if len(diff) > max_lines:
        print(f"... diff truncated ({len(diff) - max_lines} additional lines omitted)")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate/check deterministic OpenAPI schema snapshots.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--update", action="store_true", help="Regenerate the snapshot file in place.")
    mode.add_argument(
        "--check", action="store_true", help="Verify generated schema matches the snapshot file."
    )
    parser.add_argument(
        "--snapshot-path",
        default=str(DEFAULT_SNAPSHOT_PATH),
        help="Path to snapshot file (default: docs/openapi.snapshot.json).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshot_path = Path(args.snapshot_path)

    schema = _build_schema()
    rendered = _to_deterministic_json(schema)

    if args.update:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rendered, encoding="utf-8")
        print(f"OpenAPI snapshot updated: {snapshot_path}")
        return 0

    if not snapshot_path.exists():
        print(f"OpenAPI snapshot is missing: {snapshot_path}", file=sys.stderr)
        print("Run: python -m scripts.openapi_snapshot --update", file=sys.stderr)
        return 2

    existing = snapshot_path.read_text(encoding="utf-8")
    if existing == rendered:
        print("OpenAPI snapshot is up to date.")
        return 0

    print("OpenAPI snapshot drift detected.", file=sys.stderr)
    old_schema = json.loads(existing)
    for note in _classify_changes(old_schema, schema):
        print(f" - {note}", file=sys.stderr)
    _print_diff(existing, rendered)
    print("Update snapshot with: python -m scripts.openapi_snapshot --update", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
