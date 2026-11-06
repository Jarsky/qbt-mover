"""Settings: environment variable, then config.ini, then default."""

import configparser
import json
import os
from dataclasses import dataclass

CONFIG_FILE = "/app/config/config.ini"
RUNTIME_DIR = "/run/qbt-mover"

MODE_RESTORE = "restore"
MODE_RUNNING = "running"
MODE_ALL = "all"
FORCE_START_MODES = (MODE_RESTORE, MODE_RUNNING, MODE_ALL)

DEFAULT_PAUSE_STATES = ["forcedUP", "stalledUP", "uploading", "queuedUP", "error"]


@dataclass(frozen=True)
class Settings:
    remote_host: str = ""
    pause_states: tuple = tuple(DEFAULT_PAUSE_STATES)
    force_start_mode: str = MODE_RESTORE
    max_pause_hours: float = 4.0
    log_file: str = "/app/logs/qbt-mover.log"
    paused_file: str = "/app/config/paused_torrents.json"
    known_hosts_file: str = "/app/config/known_hosts"
    qbt_config: str = f"{RUNTIME_DIR}/qbt.toml"
    passphrase_file: str = f"{RUNTIME_DIR}/ssh_passphrase"
    askpass: str = "/usr/local/libexec/qbt-mover-askpass"
    lock_file: str = f"{RUNTIME_DIR}/run.lock"
    problems: tuple = ()


def parse_list(value):
    """Accept a JSON list or a comma-separated string."""
    value = value.strip()
    if value.startswith("["):
        return [str(item) for item in json.loads(value)]
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings(config_file=CONFIG_FILE, env=None):
    env = os.environ if env is None else env
    parser = configparser.ConfigParser()
    parser.read(config_file)

    def get(name, default=""):
        return env.get(name.upper()) or parser.get("settings", name, fallback=default)

    problems = []

    def get_list(name, default):
        raw = get(name)
        if not raw:
            return default
        try:
            return parse_list(raw)
        except ValueError:
            problems.append(f"Invalid {name}={raw!r}; using the default")
            return default

    mode = get("force_start_mode", MODE_RESTORE).strip().lower()
    if mode not in FORCE_START_MODES:
        # Never refuse to run: a bad setting must not leave torrents paused.
        problems.append(f"Invalid force_start_mode={mode!r}; using {MODE_RESTORE!r}")
        mode = MODE_RESTORE

    try:
        max_pause_hours = float(get("max_pause_hours", "4"))
    except ValueError:
        problems.append("Invalid max_pause_hours; using 4")
        max_pause_hours = 4.0

    # qBittorrent reports "error"; accept the old "errored" spelling from existing configs
    pause_states = ["error" if s == "errored" else s for s in get_list("states", DEFAULT_PAUSE_STATES)]

    return Settings(
        remote_host=get("remote_host"),
        pause_states=tuple(pause_states),
        force_start_mode=mode,
        max_pause_hours=max_pause_hours,
        log_file=get("log_file", Settings.log_file),
        paused_file=get("paused_torrents_file", Settings.paused_file),
        known_hosts_file=get("known_hosts_file", Settings.known_hosts_file),
        problems=tuple(problems),
    )
