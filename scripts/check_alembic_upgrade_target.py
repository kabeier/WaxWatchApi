from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_PATHS = [
    ROOT / "Makefile",
    ROOT / ".github" / "workflows",
    ROOT / "scripts",
]
SKIP_PATHS = {
    ROOT / "CHANGELOG.md",
    Path(__file__).resolve(),
}
PATTERN = re.compile(r"alembic\s+upgrade\s+head\b")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in CHECK_PATHS:
        if path.is_file():
            files.append(path)
            continue
        for child in path.rglob("*"):
            if child.is_file():
                files.append(child)
    return files


def main() -> int:
    violations: list[tuple[Path, int, str]] = []
    for file_path in iter_files():
        if file_path in SKIP_PATHS:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if 'echo "' in line:
                continue
            if PATTERN.search(line):
                violations.append((file_path, line_no, line.strip()))

    if violations:
        print("Found singular Alembic target 'head'; use 'heads' for multi-head compatibility.")
        for file_path, line_no, line in violations:
            rel = file_path.relative_to(ROOT)
            print(f" - {rel}:{line_no}: {line}")
        return 1

    print("ok: no singular alembic upgrade head invocations found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
