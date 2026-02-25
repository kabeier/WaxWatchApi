from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_SAMPLE = ROOT / ".env.sample"
CONFIG_PY = ROOT / "app/core/config.py"


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


def parse_settings_fields(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            fields: set[str] = set()
            for item in node.body:
                if not isinstance(item, ast.AnnAssign):
                    continue
                if not isinstance(item.target, ast.Name):
                    continue
                field_name = item.target.id
                if field_name.startswith("_"):
                    continue
                fields.add(field_name.upper())
            return fields

    raise RuntimeError("Could not find Settings class in app/core/config.py")


def main() -> int:
    env_keys = parse_env_keys(ENV_SAMPLE)
    settings_keys = parse_settings_fields(CONFIG_PY)
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
