from __future__ import annotations

from bd1.doctor import CheckResult, gh_version_ok, run_checks


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


def test_run_checks_flags_empty_dspy_model():
    results = run_checks(binaries=(), which=lambda name: None, runner=None, dspy_model="  ")
    by_name = {result.name: result for result in results}
    assert by_name["dspy_model"].ok is False
