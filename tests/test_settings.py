import pytest

from qbt_mover.settings import load_settings, parse_list


def write_config(tmp_path, body):
    path = tmp_path / "config.ini"
    path.write_text(f"[settings]\n{body}\n")
    return str(path)


def test_defaults_without_a_config_file(tmp_path):
    settings = load_settings(str(tmp_path / "missing.ini"), env={})
    assert settings.force_start_mode == "restore"
    assert "queuedUP" in settings.pause_states
    assert settings.problems == ()


def test_environment_beats_config_file(tmp_path):
    config = write_config(tmp_path, "remote_host = root@config\nforce_start_mode = running")
    settings = load_settings(config, env={"REMOTE_HOST": "root@env", "FORCE_START_MODE": "ALL"})
    assert settings.remote_host == "root@env"
    assert settings.force_start_mode == "all"


def test_invalid_mode_falls_back_to_restore_and_reports(tmp_path):
    settings = load_settings(str(tmp_path / "missing.ini"), env={"FORCE_START_MODE": "everything"})
    assert settings.force_start_mode == "restore"
    assert "force_start_mode" in settings.problems[0]


def test_old_errored_spelling_and_unknown_keys_are_accepted(tmp_path):
    config = write_config(tmp_path, 'states = ["stalledUP", "errored"]\nsleep_duration = 600\ncount_max = 6')
    assert load_settings(config, env={}).pause_states == ("stalledUP", "error")


@pytest.mark.parametrize("value", ['["a", "b"]', "a,b", " a , b ,"])
def test_parse_list(value):
    assert parse_list(value) == ["a", "b"]


def test_invalid_json_list_reports_and_uses_default(tmp_path):
    settings = load_settings(str(tmp_path / "missing.ini"), env={"STATES": "[broken"})
    assert "queuedUP" in settings.pause_states
    assert settings.problems
