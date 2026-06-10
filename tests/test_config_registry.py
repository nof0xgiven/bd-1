from dataclasses import replace

import pytest

from bd1.config import default_workspace_config, load_workspace_config, write_workspace_config
from bd1.errors import WorkspaceConfigError
from bd1.registry import WorkspaceRegistry


def test_workspace_config_handles_quotes_and_newlines(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    config = default_workspace_config(
        name="demo",
        repo_path=str(repo),
        product_description='Demo "quoted"\nproduct',
        setup_script="scripts/setup.sh",
        default_branch="main",
    )

    write_workspace_config(repo, config)

    assert load_workspace_config(repo) == config


def test_registry_round_trips_workspace(tmp_path):
    config = default_workspace_config("demo", "/repo", "Demo", "", "main")
    registry = WorkspaceRegistry(tmp_path)

    registry.add(config)

    assert registry.get("demo") == config
    assert registry.list_workspaces() == [config]


def test_registry_get_prefers_live_workspace_config(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = default_workspace_config(name="demo", repo_path=str(repo), product_description="demo")
    write_workspace_config(repo, config)
    registry = WorkspaceRegistry(tmp_path / "state")
    registry.add(config)

    edited = replace(config, max_attempts=9)
    write_workspace_config(repo, edited)

    assert registry.get("demo").max_attempts == 9


def test_registry_get_falls_back_to_snapshot_when_repo_config_missing(tmp_path):
    config = default_workspace_config(
        name="gone", repo_path=str(tmp_path / "missing"), product_description="demo"
    )
    registry = WorkspaceRegistry(tmp_path / "state")
    registry.add(config)
    assert registry.get("gone").max_attempts == config.max_attempts


def test_registry_get_rejects_live_config_with_mismatched_name(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = default_workspace_config(name="demo", repo_path=str(repo), product_description="demo")
    write_workspace_config(repo, config)
    registry = WorkspaceRegistry(tmp_path / "state")
    registry.add(config)

    write_workspace_config(repo, replace(config, name="other"))

    with pytest.raises(WorkspaceConfigError) as exc:
        registry.get("demo")

    assert "other" in str(exc.value)


def test_registry_get_wraps_malformed_live_toml_as_workspace_config_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = default_workspace_config(name="demo", repo_path=str(repo), product_description="demo")
    write_workspace_config(repo, config)
    registry = WorkspaceRegistry(tmp_path / "state")
    registry.add(config)

    (repo / ".bd-1.toml").write_text("not = [valid\n", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as exc:
        registry.get("demo")

    assert str(repo / ".bd-1.toml") in str(exc.value)


def test_load_workspace_config_supports_existing_files_without_pr_fields(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".bd-1.toml").write_text(
        "\n".join(
            [
                'name = "demo"',
                f'repo_path = "{repo}"',
                'default_branch = "main"',
                'product_description = "Demo"',
                'setup_script = ""',
                "max_attempts = 5",
                'pi_command = "pi"',
                'pi_model = ""',
                'pi_provider = ""',
                'vet_command = "vet"',
                'vet_model = "flash"',
                "vet_confidence_threshold = 0.8",
                'dspy_model = "openai/gpt-5-mini"',
                'dirty_exit_prompt = "commit and resolve before exit"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_workspace_config(repo)

    assert config.pr_command == "gh"
    assert config.pr_monitor_wait_seconds == 600
    assert config.max_pr_feedback_attempts == 3
    assert config.max_pr_monitor_polls == 6
    assert config.pr_base_branch == ""
    assert config.pr_draft is False
    assert config.pr_comment_ignore_authors == []
    assert config.discovery_mcp_servers == []


def test_workspace_config_round_trips_discovery_mcp_servers(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    servers = ["npx -y exa-mcp-server", "npx -y @upstash/context7-mcp"]
    config = replace(
        default_workspace_config("demo", str(repo), "Demo"),
        discovery_mcp_servers=servers,
    )

    write_workspace_config(repo, config)
    loaded = load_workspace_config(repo)

    assert loaded.discovery_mcp_servers == servers
    assert default_workspace_config("demo", str(repo), "Demo").discovery_mcp_servers == []


def test_load_workspace_config_names_unknown_keys(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = default_workspace_config("demo", str(repo), "Demo")
    write_workspace_config(repo, config)
    with (repo / ".bd-1.toml").open("a", encoding="utf-8") as handle:
        handle.write('worktree_root_policy = "global"\n')

    with pytest.raises(WorkspaceConfigError) as exc:
        load_workspace_config(repo)

    assert "worktree_root_policy" in str(exc.value)


def test_registry_wraps_corrupt_registry_json_as_workspace_config_error(tmp_path):
    registry = WorkspaceRegistry(tmp_path / "state")
    registry.path.parent.mkdir(parents=True, exist_ok=True)
    registry.path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError) as exc:
        registry.list_workspaces()

    assert "Corrupt workspace registry" in str(exc.value)
    assert str(registry.path) in str(exc.value)
