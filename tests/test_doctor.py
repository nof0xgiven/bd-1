from __future__ import annotations

from bd1.doctor import CheckResult, gh_version_ok, run_checks
from bd1.errors import CommandStartError
from bd1.subprocesses import CommandResult


def test_gh_version_ok_parses_real_output():
    assert gh_version_ok("gh version 2.62.0 (2024-11-14)\nhttps://...") is True
    assert gh_version_ok("gh version 2.40.1 (2023-12-13)") is False
    assert gh_version_ok("garbage") is False


def test_run_checks_reports_missing_binaries(tmp_path):
    def fake_which(name: str) -> str | None:
        return "/usr/bin/git" if name == "git" else None

    def fake_run(command, *, cwd, env=None, timeout=None):
        raise AssertionError("must not run commands for missing binaries")

    results = run_checks(
        binaries=("git", "pi", "vet", "gh"),
        which=fake_which,
        runner=fake_run,
        dspy_model="openai/gpt-5-mini",
    )
    by_name = {result.name: result for result in results}
    assert by_name["binary:git"] == CheckResult("binary:git", True, "/usr/bin/git")
    assert by_name["binary:pi"].ok is False
    assert by_name["dspy_model"].ok is True


def test_run_checks_keeps_diagnosing_when_gh_probe_raises():
    def raising_run(command, *, cwd, env=None, timeout=None):
        raise CommandStartError("Unable to start command: gh --version: permission denied")

    results = run_checks(
        binaries=("git", "gh"),
        which=lambda name: f"/usr/bin/{name}",
        runner=raising_run,
        dspy_model="openai/gpt-5-mini",
    )
    by_name = {result.name: result for result in results}
    assert by_name["gh:version"].ok is False
    assert "permission denied" in by_name["gh:version"].detail
    assert by_name["dspy_model"].ok is True


def test_run_checks_uses_stderr_when_gh_probe_fails_silently():
    def failing_run(command, *, cwd, env=None, timeout=None):
        return CommandResult(exit_code=1, stdout="", stderr="boom\nmore", command=list(command))

    results = run_checks(
        binaries=("gh",),
        which=lambda name: f"/usr/bin/{name}",
        runner=failing_run,
        dspy_model="openai/gpt-5-mini",
    )
    by_name = {result.name: result for result in results}
    assert by_name["gh:version"].ok is False
    assert by_name["gh:version"].detail == "boom"


def test_run_checks_flags_empty_dspy_model():
    results = run_checks(binaries=(), which=lambda name: None, runner=None, dspy_model="  ")
    by_name = {result.name: result for result in results}
    assert by_name["dspy_model"].ok is False
