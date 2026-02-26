from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DOC = "docs/FRONTEND_API_CONTRACT.md"
WATCHED_PREFIXES = ("app/api/", "app/schemas/")
SCHEMA_ARTIFACT = "docs/openapi.snapshot.json"


def git(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def git_ref_exists(ref: str) -> bool:
    if not ref:
        return False
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def detect_base_ref() -> str:
    preferred = (
        os.getenv("CONTRACT_DIFF_BASE") or os.getenv("POLICY_DIFF_BASE") or os.getenv("GITHUB_BASE_REF")
    )
    candidates = [preferred, f"origin/{preferred}" if preferred else "", "origin/main", "main", "HEAD~1"]
    for candidate in candidates:
        if candidate and git_ref_exists(candidate):
            return candidate
    return ""


def changed_files(base_ref: str) -> set[str]:
    if not base_ref:
        return set()
    merge_base = git("merge-base", base_ref, "HEAD")
    names = git("diff", "--name-only", merge_base)
    return {line.strip() for line in names.splitlines() if line.strip()}


def main() -> int:
    base_ref = detect_base_ref()
    if not base_ref:
        print("warning: no base ref found; skipping contract sync check")
        return 0

    diff_files = changed_files(base_ref)
    api_facing_changes = sorted(
        path for path in diff_files if any(path.startswith(prefix) for prefix in WATCHED_PREFIXES)
    )
    schema_artifact_changed = SCHEMA_ARTIFACT in diff_files

    if not api_facing_changes and not schema_artifact_changed:
        print("ok: no API schema/contract changes detected")
        return 0

    if CONTRACT_DOC not in diff_files:
        print("Contract sync violation detected.")
        if api_facing_changes:
            print("The following API-facing files changed:")
            for path in api_facing_changes:
                print(f" - {path}")
        if schema_artifact_changed:
            print(f"Schema artifact changed: {SCHEMA_ARTIFACT}")
        print(f"Expected an update to: {CONTRACT_DOC}")
        print(
            "Please update contract version/changelog and any endpoint/schema notes in docs/FRONTEND_API_CONTRACT.md."
        )
        return 1

    print("ok: contract sync check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
