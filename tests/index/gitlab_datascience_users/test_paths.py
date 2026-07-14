from open_pulse_sources.index.gitlab_datascience_users.config import load_config
from open_pulse_sources.index.gitlab_datascience_users.paths import get_gitlab_datascience_users_paths


def test_duckdb_path_layout():
    p = get_gitlab_datascience_users_paths().duckdb_path
    assert p.as_posix().endswith(
        "gitlab_datascience_users/duckdb/gitlab_datascience_users.duckdb",
    )


def test_config_loads():
    cfg = load_config()
    assert cfg.gitlab.host == "gitlab.datascience.ch"
    assert cfg.gitlab.collection == "gitlab_datascience_users"
