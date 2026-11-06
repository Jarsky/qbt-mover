"""Pause torrents, run the mover, resume them, and apply the force-start mode."""

import json
import os
import time
from collections import Counter
from datetime import datetime

from . import TESTED_QB_VERSION, __version__
from .log import logger
from .settings import MODE_ALL, MODE_RUNNING

STOPPED_STATES = ("pausedUP", "pausedDL", "stoppedUP", "stoppedDL")
# States that count as running when the mover pauses a torrent
RUNNING_STATES = ("forcedUP", "stalledUP", "uploading", "queuedUP")
BROKEN_STATES = ("error", "missingFiles")
RESUME_SETTLE_ATTEMPTS = 3
RESUME_SETTLE_SECONDS = 2


def format_counts(counts):
    return ", ".join(f"{count} {state}" for state, count in sorted(counts.items())) or "none"


def was_forced(torrent):
    return bool(torrent.get("force_start")) or "forced" in torrent.get("original_state", "").lower()


def wants_force(torrent, mode):
    """Should this paused torrent come back force-started under this mode?"""
    if mode == MODE_ALL or was_forced(torrent):
        return True
    return mode == MODE_RUNNING and torrent.get("original_state") in RUNNING_STATES


def resume_state_ok(forced, current_state):
    if current_state == "unknown" or current_state in STOPPED_STATES:
        return False
    # A broken torrent was resumed; retrying can't fix it
    if forced and current_state not in BROKEN_STATES:
        return "forced" in current_state.lower()
    return True


class Mover:
    def __init__(self, settings, qb, remote, sleep=time.sleep):
        self.settings = settings
        self.qb = qb
        self.remote = remote
        self.sleep = sleep

    # Paused-torrent state file

    def load_paused(self):
        try:
            with open(self.settings.paused_file) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return []
        except ValueError:
            logger.warning("Could not read %s; treating as empty", self.settings.paused_file)
            return []

    def save_paused(self, paused):
        # Replace atomically: losing this file leaves torrents stopped for good
        temp = f"{self.settings.paused_file}.tmp"
        with open(temp, "w") as handle:
            json.dump(paused, handle, indent=2)
        os.replace(temp, self.settings.paused_file)
        logger.info("Saved paused torrent state: count=%d", len(paused))

    def clear_paused(self):
        try:
            os.remove(self.settings.paused_file)
        except FileNotFoundError:
            pass

    def paused_hours(self, paused):
        stamps = []
        for torrent in paused:
            try:
                stamps.append(datetime.fromisoformat(torrent.get("paused_at", "")))
            except ValueError:
                continue
        return (datetime.now() - min(stamps)).total_seconds() / 3600 if stamps else 0.0

    # Commands

    def _client_summary(self):
        version = self.qb.version()
        torrents = self.qb.list_torrents() if version is not None else None
        if torrents is None:
            logger.error("qBittorrent-cli connectivity check failed")
            return None
        logger.info(
            "qBittorrent-cli connected: client=%s api=%s total_torrents=%d",
            version.get("app_version", "unknown"),
            version.get("api_version", "unknown"),
            len(torrents),
        )
        logger.info("qB state summary: %s", format_counts(Counter(t.get("state", "unknown") for t in torrents)))
        return torrents

    def pause(self):
        """Pause torrents that would block the mover, then start the mover."""
        torrents = self._client_summary()
        if torrents is None:
            return False
        if not self.remote.check():
            logger.error("Skipping mover start due to SSH connection failure")
            return False

        # Keep anything a previous run paused but never resumed; forgetting those
        # would leave them stopped for good.
        current = {t.get("hash") for t in torrents}
        carried = [t for t in self.load_paused() if t.get("hash") in current]
        if carried:
            logger.warning("Carrying over %d torrent(s) still paused from a previous run", len(carried))
        carried_hashes = {t.get("hash") for t in carried}

        now = datetime.now().isoformat()
        to_pause = [
            {
                "hash": t.get("hash"),
                "name": t.get("name"),
                "original_state": t.get("state"),
                "force_start": bool(t.get("force_start", False)),
                "paused_at": now,
                "size": t.get("size", 0),
                "progress": t.get("progress", 0),
            }
            for t in torrents
            if t.get("state") in self.settings.pause_states and t.get("hash") not in carried_hashes
        ]
        if to_pause:
            if not self.qb.pause([t["hash"] for t in to_pause]):
                if carried:
                    self.save_paused(carried)
                return False
            self.save_paused(carried + to_pause)
            counts = Counter(t["original_state"] for t in to_pause)
            logger.info("Pause result: paused=%d by_state=%s", len(to_pause), format_counts(counts))
        else:
            if carried:
                self.save_paused(carried)
            logger.info("Pause result: paused=0 (no matching torrent states)")

        logger.info("Starting mover on Unraid via SSH")
        return self.remote.start_mover()

    def resume(self):
        """Resume what pause() stopped and apply the force-start mode."""
        paused = self.load_paused()
        if not paused:
            logger.info("Resume result: resumed=0 (no paused state file)")
            return True

        # Drop torrents removed from the client while paused; they can never resume
        states = self.qb.states_by_hash([t.get("hash") for t in paused])
        if states is None:
            logger.error("Could not read torrent list; keeping paused state file for next retry")
            return False
        remaining = [t for t in paused if t.get("hash") in states]
        if len(remaining) != len(paused):
            logger.info("Dropping %d paused torrent(s) no longer in the client", len(paused) - len(remaining))
        if not remaining:
            self.clear_paused()
            return True
        paused = remaining

        mode = self.settings.force_start_mode
        hashes = [t["hash"] for t in paused]
        force_hashes = [t["hash"] for t in paused if wants_force(t, mode)]
        force_set = set(force_hashes)
        counts = Counter(t.get("original_state", "unknown") for t in paused)
        logger.info("Resume plan: target=%d mode=%s by_state=%s", len(hashes), mode, format_counts(counts))

        if not self.qb.resume(hashes):
            return False
        if force_hashes:
            ok = self.qb.set_force_start(force_hashes)
            logger.info("Force-start on resume: target=%d success=%s", len(force_hashes), ok)

        # qBittorrent can take a moment to leave the stopped state
        for _ in range(RESUME_SETTLE_ATTEMPTS):
            states = self.qb.states_by_hash(hashes) or {}
            if all(resume_state_ok(t["hash"] in force_set, states.get(t["hash"], "unknown")) for t in paused):
                break
            self.sleep(RESUME_SETTLE_SECONDS)

        states = self.qb.states_by_hash(hashes)
        if states is None:
            logger.warning("Could not verify resume; keeping paused state file for next retry")
            return False
        still_paused = [
            t
            for t in paused
            # "unknown" here means removed from the client in the meantime
            if t["hash"] in states and not resume_state_ok(t["hash"] in force_set, states[t["hash"]])
        ]
        post = Counter(states.get(h, "unknown") for h in hashes)
        logger.info(
            "Resume result: attempted=%d restored=%d pending=%d",
            len(paused),
            len(paused) - len(still_paused),
            len(still_paused),
        )
        logger.info("Resume post-state summary: %s", format_counts(post))
        if still_paused:
            self.save_paused(still_paused)
            names = ", ".join((t.get("name") or t["hash"][:8])[:60] for t in still_paused[:5])
            logger.warning("%d torrent(s) still not active; will retry: %s", len(still_paused), names)
            return False
        self.clear_paused()
        return True

    def force_start_pass(self):
        """In "all" mode, force-start every torrent in the client, except while the mover has torrents paused."""
        if self.settings.force_start_mode != MODE_ALL:
            return True
        if self.load_paused():
            logger.info("Force-start pass: skipped (torrents still paused for the mover)")
            return True
        torrents = self.qb.list_torrents()
        if torrents is None:
            return False
        eligible = [t for t in torrents if not t.get("force_start")]
        if not eligible:
            logger.info("Force-start pass: nothing to do")
            return True
        ok = self.qb.set_force_start([t["hash"] for t in eligible])
        counts = Counter(t["state"] for t in eligible)
        logger.info("Force-start pass: target=%d by_state=%s success=%s", len(eligible), format_counts(counts), ok)
        return ok

    def scheduled(self):
        """The recurring job: resume once the mover is done, then run the force-start pass."""
        if self._client_summary() is None:
            return False
        paused = self.load_paused()
        ok = True
        if paused:
            age = self.paused_hours(paused)
            # Seeding must never depend on the NAS being reachable. Unraid's mover just
            # skips files that are open, so resuming early is harmless.
            if not self.remote.check():
                logger.warning("SSH to Unraid failed; resuming anyway (fail-safe, paused %.1fh)", age)
                ok = self.resume()
            elif not self.remote.mover_running():
                logger.info("Mover status: stopped -> running resume flow")
                ok = self.resume()
            elif age >= self.settings.max_pause_hours:
                logger.warning(
                    "Mover still running but torrents paused %.1fh >= %sh; resuming anyway",
                    age,
                    self.settings.max_pause_hours,
                )
                ok = self.resume()
            else:
                logger.info(
                    "Mover status: running (resume skipped, paused %.1fh of max %sh)",
                    age,
                    self.settings.max_pause_hours,
                )
        else:
            logger.info("Resume result: resumed=0 (no paused state file)")
        return self.force_start_pass() and ok


def run_header(command):
    logger.info("qbt-mover v%s (tested qBittorrent %s)", __version__, TESTED_QB_VERSION)
    logger.info("Run started: command=%s", command)
