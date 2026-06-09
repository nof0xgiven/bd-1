from bd1.config import default_workspace_config, load_workspace_config, write_workspace_config
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
