from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "check_change_surface.py"
    spec = importlib.util.spec_from_file_location("check_change_surface", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_task_orchestration_trigger_matches_app_tasks_py():
    module = _load_module()

    assert module.matches_any("app/tasks.py", module.TRIGGER_GLOBS["task orchestration"])


def test_main_enforces_governance_for_app_tasks_py(monkeypatch, capsys):
    module = _load_module()

    monkeypatch.setattr(module, "detect_base_ref", lambda: "main")
    monkeypatch.setattr(module, "changed_files", lambda _base_ref: {"app/tasks.py"})

    rc = module.main()

    assert rc == 1
    output = capsys.readouterr().out
    assert "Triggered categories:" in output
    assert " - task orchestration" in output
    assert " - missing required file update: Makefile" in output
    assert " - missing required file update: .github/workflows/ci.yml" in output
    assert " - missing required file update: .env.sample" in output
    assert "Integration hygiene violation: missing CHANGELOG.md update" in output


def test_remediation_message_lists_required_sync_artifacts(monkeypatch, capsys):
    module = _load_module()

    monkeypatch.setattr(module, "detect_base_ref", lambda: "main")
    monkeypatch.setattr(module, "changed_files", lambda _base_ref: {"app/tasks.py"})

    rc = module.main()

    assert rc == 1
    output = capsys.readouterr().out
    assert module.remediation_message() in output


def test_remediation_message_is_derived_from_required_files():
    module = _load_module()

    assert (
        module.remediation_message()
        == "Remediation: update .env.sample, .github/workflows/ci.yml, Makefile, "
        "CHANGELOG.md, and relevant documentation in the same PR."
    )
