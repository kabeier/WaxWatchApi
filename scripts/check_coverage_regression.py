from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_COVERAGE = ROOT / "coverage.json"
BASE_COVERAGE = ROOT / "coverage.base.json"

WARNING_THRESHOLD_PERCENT = 0.0
FAILURE_THRESHOLD_PERCENT = 1.0

HIGH_RISK_MODULES = {
    "app/services/background.py": "Background dispatch and orchestration",
    "app/services/watch_rules.py": "Watch rule mutation/validation",
    "app/services/matching.py": "Matching and candidate scoring",
    "app/core/token_crypto.py": "Access-token encryption/decryption",
}


def load_coverage(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"coverage file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_key(path: str) -> str:
    marker = "app/"
    if marker in path:
        return path[path.index(marker) :]
    return path.replace("\\", "/")


def module_percent(report: dict, module_path: str) -> float | None:
    files = report.get("files", {})
    for file_path, payload in files.items():
        if normalize_key(file_path) == module_path:
            summary = payload.get("summary", {})
            covered = summary.get("covered_lines", 0)
            total = summary.get("num_statements", 0)
            if total <= 0:
                return None
            return (covered / total) * 100
    return None


def total_percent(report: dict) -> float:
    totals = report.get("totals", {})
    covered = totals.get("covered_lines", 0)
    total = totals.get("num_statements", 0)
    if total <= 0:
        raise ValueError("coverage report has no measured statements")
    return (covered / total) * 100


def _regression_delta(current: float, base: float) -> float:
    return max(base - current, 0.0)


def main() -> int:
    try:
        current = load_coverage(CURRENT_COVERAGE)
        base = load_coverage(BASE_COVERAGE)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"coverage regression check failed to load reports: {exc}")
        return 1

    failures: list[str] = []
    warnings: list[str] = []

    current_total = total_percent(current)
    base_total = total_percent(base)
    total_delta = _regression_delta(current_total, base_total)
    if total_delta > FAILURE_THRESHOLD_PERCENT:
        failures.append(
            f"total coverage regressed by {total_delta:.2f}%: current={current_total:.2f}% < base={base_total:.2f}%"
        )
    elif total_delta > WARNING_THRESHOLD_PERCENT:
        warnings.append(
            f"total coverage regressed by {total_delta:.2f}%: current={current_total:.2f}% < base={base_total:.2f}%"
        )

    for module_path, description in HIGH_RISK_MODULES.items():
        current_pct = module_percent(current, module_path)
        base_pct = module_percent(base, module_path)
        if current_pct is None or base_pct is None:
            failures.append(f"missing high-risk module coverage entry for {module_path} ({description})")
            continue
        module_delta = _regression_delta(current_pct, base_pct)
        if module_delta > FAILURE_THRESHOLD_PERCENT:
            failures.append(
                "high-risk module regressed by "
                f"{module_delta:.2f}%: {module_path} current={current_pct:.2f}% < base={base_pct:.2f}% ({description})"
            )
        elif module_delta > WARNING_THRESHOLD_PERCENT:
            warnings.append(
                "high-risk module regressed by "
                f"{module_delta:.2f}%: {module_path} current={current_pct:.2f}% < base={base_pct:.2f}% ({description})"
            )

    print(f"total coverage: current={current_total:.2f}% | base={base_total:.2f}%")
    for module_path in HIGH_RISK_MODULES:
        current_pct = module_percent(current, module_path)
        base_pct = module_percent(base, module_path)
        if current_pct is not None and base_pct is not None:
            print(f"high-risk module: {module_path} current={current_pct:.2f}% | base={base_pct:.2f}%")

    if warnings:
        print("coverage regression gate warning:")
        for warning in warnings:
            print(f" - {warning}")

    if failures:
        print("coverage regression gate failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("ok: coverage regression checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
