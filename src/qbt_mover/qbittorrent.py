"""qBittorrent access: qbittorrent-cli, plus the Web API for what the CLI can't do."""

import http.cookiejar
import json
import subprocess
import tomllib
import urllib.parse
import urllib.request

from .log import logger

API_TIMEOUT = 60  # setForceStart on hundreds of torrents can take a while


class QBittorrent:
    def __init__(self, settings):
        self.config = settings.qbt_config

    def _run(self, *args):
        command = ["qbt", *args, "--config", self.config]
        description = " ".join(["qbt", *args[:2]])
        result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            logger.error("%s failed (exit %s)", description, result.returncode)
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    logger.error("%s: %s", description, stream.decode(errors="replace").strip())
        return result

    def _run_json(self, *args):
        result = self._run(*args)
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout.decode(errors="replace"))
        except ValueError as exc:
            logger.error("qbt %s returned invalid JSON: %s", " ".join(args[:2]), exc)
            return None

    def version(self):
        return self._run_json("app", "version", "--output", "json")

    def list_torrents(self):
        """All torrents, or None if the client can't be queried. Callers must not
        mistake a failed query for "all torrents were deleted"."""
        return self._run_json("torrent", "list", "--output", "json")

    def states_by_hash(self, hashes):
        torrents = self.list_torrents()
        if torrents is None:
            return None
        wanted = set(hashes)
        return {t.get("hash"): t.get("state", "unknown") for t in torrents if t.get("hash") in wanted}

    def pause(self, hashes):
        return self._run("torrent", "pause", "--hashes", ",".join(hashes)).returncode == 0

    def resume(self, hashes):
        return self._run("torrent", "resume", "--hashes", ",".join(hashes)).returncode == 0

    def _connection(self):
        with open(self.config, "rb") as handle:
            qb = tomllib.load(handle).get("qbittorrent", {})
        return qb.get("addr", "http://127.0.0.1:8080").rstrip("/"), qb.get("login", ""), qb.get("password", "")

    def set_force_start(self, hashes):
        """Turn force-start on through the Web API. Returns True on success."""
        if not hashes:
            return True
        try:
            base_url, login, password = self._connection()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            if login:
                data = urllib.parse.urlencode({"username": login, "password": password}).encode()
                with opener.open(f"{base_url}/api/v2/auth/login", data=data, timeout=API_TIMEOUT) as response:
                    if response.read().decode(errors="replace").strip() == "Fails.":
                        logger.error("qB Web API authentication failed; cannot set force-start")
                        return False
            data = urllib.parse.urlencode({"hashes": "|".join(hashes), "value": "true"}).encode()
            with opener.open(f"{base_url}/api/v2/torrents/setForceStart", data=data, timeout=API_TIMEOUT):
                pass
            return True
        except Exception as exc:
            logger.error("Failed to set force-start via qB Web API: %s", exc)
            return False
