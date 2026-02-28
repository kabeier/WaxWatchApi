from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRIGGER_GLOBS: dict[str, tuple[str, ...]] = {
    "testing workflow": (
        "tests/**",
        "docker-compose.test.yml",
        "pytest.ini",
        "pyproject.toml",
        "scripts/schema_drift_check.py",
    ),
    "CI config": (
        ".github/workflows/**",
        ".pre-commit-config.yaml",
    ),
    "task orchestration": (
        "Makefile",
        "docker-compose*.yml",
        "app/tasks.py",
        "app/tasks/**",
        "app/worker.py",
    ),
    "settings": (
        "app/core/config.py",
        ".env.sample",
        ".env.dev",
    ),
}

REQUIRED_FILES = {
    "Makefile",
    ".github/workflows/ci.yml",
}
CHANGELOG_FILE = "CHANGELOG.md"
DOC_GLOBS = (
    "CONTRIBUTING.md",
    "docs/**/*.md",
)
CHANGELOG_ALWAYS_REQUIRED_GLOBS = (
    "app/api/**",
    "app/schemas/**",
    "app/services/**",
    "app/core/config.py",
    "Makefile",
    ".github/workflows/**",
    "alembic/**",
)
CHANGELOG_EXCEPTION_ONLY_GLOBS = (
    "tests/**",
    "pytest.ini",
    "docker-compose.test.yml",
    "scripts/schema_drift_check.py",
    "scripts/check_change_surface.py",
    "scripts/check_env_sample.py",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
    "docs/**/*.md",
)


def env_contract_change_detected(diff_files: set[str]) -> bool:
    """Return True when env sample synchronization is expected.

    Policy: `.env.sample` updates are only required when env variables are
    added/removed or defaults change. In practice, that means env/config
    contract files are part of the same PR change surface.
    """

    return any(path in diff_files for path in {"app/core/config.py", ".env.sample"})


def remediation_message(*, require_env_sample: bool) -> str:
    required_files = set(REQUIRED_FILES)
    if require_env_sample:
        required_files.add(".env.sample")
    required_files_text = ", ".join(sorted(required_files))
    env_sample_note = (
        ""
        if require_env_sample
        else " (update `.env.sample` only for env var additions/removals/default changes)"
    )
    return (
        f"Remediation: update {required_files_text}, {CHANGELOG_FILE}, and relevant documentation in the same PR."
        f"{env_sample_note}"
    )


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
    preferred = os.getenv("POLICY_DIFF_BASE") or os.getenv("GITHUB_BASE_REF")
    candidates = [preferred, f"origin/{preferred}" if preferred else "", "origin/main", "main", "HEAD~1"]
    for candidate in candidates:
        if candidate and git_ref_exists(candidate):
            return candidate
    return ""


def changed_files(base_ref: str) -> set[str]:
    if not base_ref:
        return set()
    merge_base = git("merge-base", base_ref, "HEAD")
    names = git("diff", "--name-only", merge_base, check=False)
    return {line.strip() for line in names.splitlines() if line.strip()}


def matches_any(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in globs)


def changelog_exception_applies(diff_files: set[str]) -> bool:
    if any(matches_any(path, CHANGELOG_ALWAYS_REQUIRED_GLOBS) for path in diff_files):
        return False
    return all(matches_any(path, CHANGELOG_EXCEPTION_ONLY_GLOBS) for path in diff_files)


def main() -> int:
    base_ref = detect_base_ref()
    if not base_ref:
        print("warning: no base ref found; skipping change-surface enforcement")
        return 0

    diff_files = changed_files(base_ref)
    if not diff_files:
        print("ok: no changed files detected")
        return 0

    matched_categories: list[str] = []
    for category, globs in TRIGGER_GLOBS.items():
        if any(matches_any(path, globs) for path in diff_files):
            matched_categories.append(category)

    if not matched_categories:
        print("ok: no integration hygiene trigger categories touched")
        return 0

    errors: list[str] = []
    require_env_sample = env_contract_change_detected(diff_files)
    required_files = set(REQUIRED_FILES)
    if require_env_sample:
        required_files.add(".env.sample")
    missing_required = sorted(required_files - diff_files)
    if missing_required:
        errors.append(
            "Integration hygiene violation: triggered change surface requires synchronized updates to all required governance files."
        )
        errors.extend(f" - missing required file update: {path}" for path in missing_required)

    docs_changed = sorted(path for path in diff_files if matches_any(path, DOC_GLOBS))
    if not docs_changed:
        errors.append(
            "Integration hygiene violation: no relevant docs update detected (expected CONTRIBUTING.md or docs/*.md changes)."
        )

    if CHANGELOG_FILE not in diff_files and not changelog_exception_applies(diff_files):
        errors.append(
            "Integration hygiene violation: missing CHANGELOG.md update for triggered change surface."
        )

    if errors:
        print("Triggered categories:")
        for category in matched_categories:
            print(f" - {category}")
        print("\n".join(errors))
        print(remediation_message(require_env_sample=require_env_sample))
        return 1

    print("Triggered categories:")
    for category in matched_categories:
        print(f" - {category}")
    print("Docs touched:")
    for path in docs_changed:
        print(f" - {path}")
    print("ok: integration hygiene change-surface checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
