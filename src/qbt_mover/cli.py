"""Command line entry point."""

import fcntl
import os
import sys
import time

from . import log
from .log import logger
from .mover import Mover, run_header
from .qbittorrent import QBittorrent
from .remote import Remote
from .settings import load_settings

USAGE = """usage: qbt-mover COMMAND

  -pause               Pause torrents and start the Unraid mover
  -force-resume-mover  Resume if the mover is done, then apply the force-start mode (scheduled job)
  -resume              Resume paused torrents now, without checking the mover
  -force-resume        Same as -resume (kept for compatibility)
  -force-start         Run the force-start pass now (only acts in "all" mode)
  -check-ssh           Test the SSH connection to Unraid, including the key passphrase
"""


def acquire_lock(path, blocking=True):
    """Serialise runs, since cron fires the pause and scheduled jobs together.
    Returns the open lock file, or None if another run holds it and blocking is False."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = open(path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def main(argv=None, settings=None):
    argv = sys.argv[1:] if argv is None else argv
    settings = settings or load_settings()
    log.configure(settings.log_file)
    for problem in settings.problems:
        logger.warning(problem)

    remote = Remote(settings)
    mover = Mover(settings, QBittorrent(settings), remote)
    commands = {
        "-pause": mover.pause,
        "-force-resume-mover": mover.scheduled,
        "-resume": mover.resume,
        "-force-resume": mover.resume,
        "-force-start": mover.force_start_pass,
        "-check-ssh": remote.check,
    }
    command = argv[0] if argv else None
    if command not in commands:
        print(USAGE, file=sys.stderr)
        return 2

    if command == "-check-ssh":
        return 0 if remote.check() else 1

    # The scheduled job recurs, so it skips a cycle rather than queueing behind another run
    lock = acquire_lock(settings.lock_file, blocking=command != "-force-resume-mover")
    if lock is None:
        logger.info("Another run is active; skipping %s this cycle", command)
        return 0

    started = time.time()
    run_header(command)
    ok = commands[command]()
    logger.info("Run completed: command=%s duration=%.2fs", command, time.time() - started)
    lock.close()
    return 0 if ok else 1
