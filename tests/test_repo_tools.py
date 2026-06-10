from __future__ import annotations

import pytest

from bd1.repo_tools import RepoTools


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def handler():\n    return 'ok'\n# marker_alpha\n", encoding="utf-8"
    )
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    return tmp_path


def test_list_tree_skips_git_dir(repo):
    listing = RepoTools(repo).list_tree()
    assert "src/app.py" in listing
    assert ".git" not in listing


def test_list_tree_truncation_marker_hints_at_narrower_subdir(repo):
    for index in range(450):
        (repo / "src" / f"gen_{index:04d}.py").write_text("pass\n", encoding="utf-8")
    listing = RepoTools(repo).list_tree()
    assert "truncated at 400 entries; call again with a narrower subdir" in listing


def test_read_file_returns_numbered_lines(repo):
    text = RepoTools(repo).read_file("src/app.py")
    assert "1: def handler():" in text


def test_read_file_blocks_path_escape(repo):
    out = RepoTools(repo).read_file("../outside.txt")
    assert "error" in out.lower()


def test_read_file_blocks_git_internals(repo):
    out = RepoTools(repo).read_file(".git/config")
    assert "error" in out.lower()


def test_search_text_finds_matches_with_paths_and_lines(repo):
    out = RepoTools(repo).search_text("marker_alpha")
    assert "src/app.py" in out and "3" in out


def test_search_text_reports_no_matches(repo):
    out = RepoTools(repo).search_text("does_not_exist_anywhere")
    assert "no matches" in out.lower()


def test_read_file_caps_output(repo):
    (repo / "big.txt").write_text("x" * 100_000, encoding="utf-8")
    out = RepoTools(repo).read_file("big.txt")
    assert len(out) < 30_000
    assert "truncated" in out.lower()


def test_read_file_reports_empty_file_without_error(repo):
    (repo / "empty.txt").write_text("", encoding="utf-8")
    assert RepoTools(repo).read_file("empty.txt") == "(empty file)"


def test_read_file_tolerates_bad_start_line(repo):
    out = RepoTools(repo).read_file("src/app.py", start_line="abc")
    assert "error" in out.lower()


def test_read_file_refuses_secret_files(repo):
    (repo / ".env").write_text("API_KEY=sk-12345678901234567890\n", encoding="utf-8")
    (repo / "server.pem").write_text("PRIVATE KEY", encoding="utf-8")
    tools = RepoTools(repo)
    assert "error" in tools.read_file(".env").lower()
    assert "error" in tools.read_file("server.pem").lower()
    assert "sk-12345678901234567890" not in tools.search_text("API_KEY")


def test_search_text_rejects_bytes_pattern(repo):
    # re.compile(b"abc") succeeds, but searching str lines would raise
    # TypeError; the guard must turn this into an observation string.
    out = RepoTools(repo).search_text(b"abc")
    assert "error" in out.lower()


def test_read_file_tolerates_pathologically_long_name(repo):
    # ENAMETOOLONG must become an observation string, not an OSError.
    out = RepoTools(repo).read_file("x" * 5000)
    assert "error" in out.lower()


def test_list_tree_tolerates_pathologically_long_name(repo):
    out = RepoTools(repo).list_tree("x" * 5000)
    assert "error" in out.lower() or "no files found" in out.lower()


def test_read_file_reports_start_line_past_eof(repo):
    out = RepoTools(repo).read_file("src/app.py", start_line=99)
    assert "error" in out.lower()
    assert "past end" in out.lower()
    assert "3" in out  # tells the model how many lines the file has


def test_search_text_does_not_follow_symlinks_out_of_repo(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "loot.txt"
    outside.write_text("TOPSECRET_PAYLOAD\n", encoding="utf-8")
    (repo / "innocent.txt").symlink_to(outside)
    out = RepoTools(repo).search_text("TOPSECRET_PAYLOAD")
    assert "TOPSECRET_PAYLOAD" not in out
    assert "no matches" in out.lower()


def test_tools_work_when_repo_parent_dir_is_named_like_a_skip_dir(tmp_path):
    # ReAct tools must judge skip-dirs by REPO-RELATIVE parts; an absolute
    # parent named e.g. "build" must not blank out the whole repo.
    root = tmp_path / "build" / "myrepo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    tools = RepoTools(root)
    assert "src/app.py" in tools.list_tree()
    assert "src/app.py" in tools.search_text("x = 1")
