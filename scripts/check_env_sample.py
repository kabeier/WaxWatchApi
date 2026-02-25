from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/waxwatch")

from app.core.config import Settings

ENV_SAMPLE = ROOT / ".env.sample"


def parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def main() -> int:
    env_keys = parse_env_keys(ENV_SAMPLE)
    settings_keys = {name.upper() for name in Settings.model_fields}
    missing = sorted(settings_keys - env_keys)

    if missing:
        print("Missing .env.sample entries for settings fields:")
        for key in missing:
            print(f" - {key}")
        return 1

    print("ok: .env.sample includes all Settings fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
