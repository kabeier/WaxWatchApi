from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DOC = "docs/FRONTEND_API_CONTRACT.md"
WATCHED_PREFIXES = ("app/api/", "app/schemas/")


def _git_lines(args: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _has_ref(ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _detect_range() -> str | None:
    explicit_base = os.getenv("API_CONTRACT_CHECK_BASE")
    if explicit_base:
        return f"{explicit_base}..HEAD"

    github_base = os.getenv("GITHUB_BASE_REF")
    if github_base:
        remote_base = f"origin/{github_base}"
        if _has_ref(remote_base):
            merge_base = subprocess.run(
                ["git", "merge-base", "HEAD", remote_base],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            base = merge_base.stdout.strip()
            if merge_base.returncode == 0 and base:
                return f"{base}..HEAD"

    if _has_ref("HEAD~1"):
        return "HEAD~1..HEAD"

    return None


def _collect_changed_files() -> set[str]:
    working_tree = _git_lines(["diff", "--name-only", "HEAD"])
    if working_tree:
        return working_tree

    compare_range = _detect_range()
    if compare_range:
        return _git_lines(["diff", "--name-only", compare_range])

    return set()


def main() -> int:
    changed_files = _collect_changed_files()
    watched_changes = sorted(
        path
        for path in changed_files
        if any(path.startswith(prefix) for prefix in WATCHED_PREFIXES)
    )

    if not watched_changes:
        print("ok: no API contract-sensitive changes detected")
        return 0

    if CONTRACT_DOC in changed_files:
        print("ok: API contract-sensitive files changed and contract doc was updated")
        return 0

    print("API-facing changes detected without updating contract documentation.")
    print("Changed API/schema files:")
    for path in watched_changes:
        print(f" - {path}")
    print(f"Required update: {CONTRACT_DOC}")
    print(
        "Workflow: update the contract version/changelog/breaking-change policy, then commit both code and doc changes together."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
