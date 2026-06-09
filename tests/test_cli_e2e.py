import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_e2e_with_fake_pi_and_vet(tmp_path, init_git_repo):
    _assert_project_runtime_ignores()
    repo = init_git_repo(tmp_path / "repo")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_pi(fake_bin / "pi")
    _write_fake_vet(fake_bin / "vet")

    env = _cli_env(tmp_path / "state", fake_bin)

    add_result = _run_cli(
        [
            "workspace",
            "add",
            "--name",
            "demo",
            "--repo",
            str(repo),
            "--product",
            "Demo fixture workspace",
        ],
        cwd=repo,
        env=env,
    )
    assert add_result.returncode == 0, add_result.stderr
    assert "Review and commit generated bd-1 workspace files" in add_result.stdout

    status_before_commit = _git(repo, ["status", "--short", "--untracked-files=all"]).stdout
    assert ".bd-1.toml" in status_before_commit
    assert ".artifacts/product.md" in status_before_commit

    _git(repo, ["add", ".bd-1.toml", ".artifacts", ".learning", ".examples"])
    _git(repo, ["commit", "-m", "add bd-1 workspace artifacts"])

    run_result = _run_cli(["run", "Make a fixture change"], cwd=repo, env=env)
    assert run_result.returncode == 0, run_result.stderr
    run_output = json.loads(run_result.stdout)
    assert run_output["state"] == "COMPLETE"

    status_result = _run_cli(["status", run_output["run_id"]], cwd=repo, env=env)
    assert status_result.returncode == 0, status_result.stderr
    status = json.loads(status_result.stdout)
    assert status["state"] == "COMPLETE"
    assert (tmp_path / "state" / "runs.db").exists()

    run_record_path = _run_record_path(tmp_path / "state", run_output["run_id"])
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    worktree = Path(run_record["worktree"])
    assert run_record_path.exists()
    assert Path(run_record["attempts"][0]["vet_output_path"]).exists()
    assert Path(run_record["attempts"][0]["review_path"]).exists()
    assert Path(run_record["artifacts"]["completed"]).exists()
    assert list((worktree / ".artifacts" / "learning").glob(f"{run_output['run_id']}-*.md"))

    (worktree / "local.db").write_text("cache\n", encoding="utf-8")
    assert _git_check_ignore(worktree, ".sessions")
    assert _git_check_ignore(worktree, "local.db")

    tracked = _git(worktree, ["ls-files", ".bd-1.toml", ".artifacts/product.md"]).stdout
    assert ".bd-1.toml" in tracked
    assert ".artifacts/product.md" in tracked


def _assert_project_runtime_ignores() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".sessions/", "*.db", "*.sqlite"):
        assert pattern in gitignore


def _cli_env(state_dir: Path, fake_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["BD1_HOME"] = str(state_dir)
    env["BD1_REASONING"] = "template"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = (
        pythonpath if not existing_pythonpath else f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    )
    return env


def _run_cli(
    args: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bd1", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def _git_check_ignore(repo: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _run_record_path(state_dir: Path, run_id: str) -> Path:
    pointer = json.loads((state_dir / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))
    return Path(pointer["run_record_path"])


def _write_fake_pi(path: Path) -> None:
    path.write_text(
        f"""#!{sys.executable}
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("-p", dest="prompt", required=True)
parser.add_argument("--session-id", required=True)
parser.add_argument("--session-dir", required=True)
parser.add_argument("--model")
parser.add_argument("--provider")
args = parser.parse_args()

session_dir = Path(args.session_dir)
session_dir.mkdir(parents=True, exist_ok=True)
(session_dir / "session.jsonl").write_text(
    "\\n".join(
        [
            json.dumps({{"type": "session", "id": args.session_id}}),
            json.dumps(
                {{
                    "type": "message",
                    "message": {{
                        "role": "assistant",
                        "content": [{{"type": "text", "text": "fake pi completed"}}],
                    }},
                }}
            ),
        ]
    )
    + "\\n",
    encoding="utf-8",
)

Path("fixture-change.txt").write_text("changed by fake pi\\n", encoding="utf-8")
subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "config", "user.name", "Test User"], check=True)
subprocess.run(["git", "add", "fixture-change.txt"], check=True)
subprocess.run(["git", "commit", "-m", "fake pi fixture change"], check=True)
print("fake pi complete")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_vet(path: Path) -> None:
    path.write_text(
        f"""#!{sys.executable}
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("task")
parser.add_argument("--repo", required=True)
parser.add_argument("--base-commit", required=True)
parser.add_argument("--model", required=True)
parser.add_argument("--history-loader", required=True)
parser.add_argument("--output-format", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--confidence-threshold")
args = parser.parse_args()

Path(args.output).write_text(json.dumps({{"issues": []}}), encoding="utf-8")
print("fake vet pass")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
