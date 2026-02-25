from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_SAMPLE = ROOT / ".env.sample"
CONFIG_PY = ROOT / "app/core/config.py"
MAKEFILE = ROOT / "Makefile"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
POLICY_DOCS = {
    "docs/DEPLOYMENT.md",
    "docs/FRONTEND_API_CONTRACT.md",
}
REQUIRED_SYNC_FILES = {
    ".env.sample",
    "Makefile",
    ".github/workflows/ci.yml",
    "CONTRIBUTING.md",
}
TARGET_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+):")


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
    return subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def detect_base_ref() -> str:
    preferred = os.getenv("POLICY_DIFF_BASE") or os.getenv("GITHUB_BASE_REF")
    candidates = [preferred, f"origin/{preferred}" if preferred else "", "origin/main", "main", "HEAD~1"]
    for candidate in candidates:
        if candidate and git_ref_exists(candidate):
            return candidate
    return ""


def parse_env_keys(content: str) -> set[str]:
    keys: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def parse_settings_fields(content: str) -> set[str]:
    tree = ast.parse(content)
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


def parse_make_targets(content: str) -> set[str]:
    targets: set[str] = set()
    for line in content.splitlines():
        if line.startswith(".") or line.startswith("\t") or "=" in line.split(":", 1)[0]:
            continue
        match = TARGET_PATTERN.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def parse_ci_run_commands(content: str) -> set[str]:
    commands: set[str] = set()
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        if stripped.startswith("run:"):
            run_value = stripped[len("run:") :].strip()
            if run_value and run_value != "|":
                commands.add(run_value)
            elif run_value == "|":
                block_indent = len(raw_line) - len(raw_line.lstrip())
                i += 1
                while i < len(lines):
                    block_line = lines[i]
                    if not block_line.strip():
                        i += 1
                        continue
                    indent = len(block_line) - len(block_line.lstrip())
                    if indent <= block_indent:
                        i -= 1
                        break
                    commands.add(block_line.strip())
                    i += 1
        i += 1
    return commands


def read_from_base(base_ref: str, path: str) -> str:
    if not base_ref:
        return ""
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def changed_files(base_ref: str) -> set[str]:
    if not base_ref:
        return set()
    merge_base = git("merge-base", base_ref, "HEAD")
    names = git("diff", "--name-only", merge_base, check=False)
    return {line.strip() for line in names.splitlines() if line.strip()}


def main() -> int:
    env_content = ENV_SAMPLE.read_text(encoding="utf-8")
    current_config = CONFIG_PY.read_text(encoding="utf-8")
    current_makefile = MAKEFILE.read_text(encoding="utf-8")
    current_ci = CI_WORKFLOW.read_text(encoding="utf-8")

    env_keys = parse_env_keys(env_content)
    settings_keys = parse_settings_fields(current_config)

    errors: list[str] = []
    notices: list[str] = []

    missing_env_entries = sorted(settings_keys - env_keys)
    if missing_env_entries:
        errors.append("Missing .env.sample entries for settings fields:")
        errors.extend(f" - {key}" for key in missing_env_entries)

    base_ref = detect_base_ref()
    diff_files = changed_files(base_ref) if base_ref else set()

    if base_ref and diff_files:
        base_config = read_from_base(base_ref, "app/core/config.py")
        base_makefile = read_from_base(base_ref, "Makefile")
        base_ci = read_from_base(base_ref, ".github/workflows/ci.yml")

        base_settings = parse_settings_fields(base_config) if base_config else set()
        base_targets = parse_make_targets(base_makefile) if base_makefile else set()
        base_ci_commands = parse_ci_run_commands(base_ci) if base_ci else set()

        current_targets = parse_make_targets(current_makefile)
        current_ci_commands = parse_ci_run_commands(current_ci)

        new_settings = sorted(settings_keys - base_settings)
        new_targets = sorted(current_targets - base_targets)
        new_ci_commands = sorted(current_ci_commands - base_ci_commands)

        if new_settings or new_targets or new_ci_commands:
            missing_sync_files = sorted(REQUIRED_SYNC_FILES - diff_files)
            if missing_sync_files:
                errors.append(
                    "Policy sync violation: this change introduces new Settings fields or new workflow-sensitive commands but did not update required governance files:"
                )
                errors.extend(f" - {path}" for path in missing_sync_files)

            changed_docs = sorted(POLICY_DOCS & diff_files)
            if not changed_docs:
                errors.append(
                    "Policy sync violation: expected at least one affected docs update (docs/DEPLOYMENT.md or docs/FRONTEND_API_CONTRACT.md)."
                )

            if new_settings:
                notices.append("Detected new Settings fields:")
                notices.extend(f" - {name}" for name in new_settings)
            if new_targets:
                notices.append("Detected new Makefile targets:")
                notices.extend(f" - {name}" for name in new_targets)
            if new_ci_commands:
                notices.append("Detected new CI run commands:")
                notices.extend(f" - {command}" for command in new_ci_commands)
    elif not base_ref:
        print("warning: no base ref found; running only .env.sample coverage check")

    if errors:
        print("\n".join(errors))
        return 1

    if notices:
        print("\n".join(notices))
    print("ok: .env.sample and governance sync checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
