import pytest

from qbt_mover.log import logger
from qbt_mover.settings import Settings


@pytest.fixture(autouse=True)
def clean_log_handlers():
    yield
    logger.handlers.clear()


class FakeQB:
    """In-memory qBittorrent: pause, resume and force-start change torrent state."""

    def __init__(self, torrents=()):
        self.torrents = {t["hash"]: dict(t) for t in torrents}
        self.forced_calls = []
        self.state_before_pause = {}
        self.fail_list = False

    def version(self):
        return {"app_version": "v5.3.0", "api_version": "2.16.2"}

    def list_torrents(self):
        return None if self.fail_list else [dict(t) for t in self.torrents.values()]

    def states_by_hash(self, hashes):
        torrents = self.list_torrents()
        if torrents is None:
            return None
        return {t["hash"]: t["state"] for t in torrents if t["hash"] in set(hashes)}

    def pause(self, hashes):
        for h in hashes:
            self.state_before_pause[h] = self.torrents[h]["state"]
            self.torrents[h].update(state="stoppedUP", force_start=False)
        return True

    def resume(self, hashes):
        for h in hashes:
            # A broken torrent stays broken when resumed
            self.torrents[h]["state"] = "error" if self.state_before_pause.get(h) == "error" else "stalledUP"
        return True

    def set_force_start(self, hashes):
        self.forced_calls.append(list(hashes))
        for h in hashes:
            self.torrents[h].update(state="forcedUP", force_start=True)
        return True

    def forced(self):
        return {h for h, t in self.torrents.items() if t.get("force_start")}


class FakeRemote:
    def __init__(self, reachable=True, running=False):
        self.reachable = reachable
        self.running = running
        self.mover_starts = 0

    def check(self):
        return self.reachable

    def mover_running(self):
        return self.running

    def start_mover(self):
        self.mover_starts += 1
        return True


def torrent(hash_, state, force_start=False):
    return {"hash": hash_, "name": f"name-{hash_}", "state": state, "force_start": force_start}


@pytest.fixture
def make_settings(tmp_path):
    def build(**overrides):
        values = {
            "remote_host": "root@tower",
            "paused_file": str(tmp_path / "paused.json"),
            "log_file": str(tmp_path / "logs" / "qbt-mover.log"),
            "known_hosts_file": str(tmp_path / "known_hosts"),
            "passphrase_file": str(tmp_path / "ssh_passphrase"),
            "lock_file": str(tmp_path / "run.lock"),
        }
        values.update(overrides)
        return Settings(**values)

    return build
