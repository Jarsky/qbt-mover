import json
import os

import pytest
from conftest import FakeQB, FakeRemote, torrent

from qbt_mover.mover import Mover, resume_state_ok, wants_force


def seeded():
    return [
        torrent("forced", "forcedUP", True),
        torrent("stalled", "stalledUP"),
        torrent("uploading", "uploading"),
        torrent("queued", "queuedUP"),
        torrent("broken", "error"),
        torrent("downloading", "downloading"),
        torrent("user-stopped", "stoppedUP"),
    ]


def cycle(settings, torrents=None):
    """A full pause, mover finished, resume cycle."""
    qb, remote = FakeQB(seeded() if torrents is None else torrents), FakeRemote()
    mover = Mover(settings, qb, remote, sleep=lambda _: None)
    assert mover.pause()
    return qb, remote, mover


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("restore", {"forced"}),
        ("running", {"forced", "stalled", "uploading", "queued"}),
        ("all", {"forced", "stalled", "uploading", "queued", "broken", "downloading", "user-stopped"}),
    ],
)
def test_mode_controls_what_is_forced_after_a_cycle(make_settings, mode, expected):
    qb, _, mover = cycle(make_settings(force_start_mode=mode))
    mover.scheduled()
    assert qb.forced() == expected
    assert not os.path.exists(mover.settings.paused_file)


@pytest.mark.parametrize("mode", ["restore", "running"])
def test_user_stopped_torrents_stay_stopped_outside_all_mode(make_settings, mode):
    qb, _, mover = cycle(make_settings(force_start_mode=mode))
    mover.scheduled()
    assert qb.torrents["user-stopped"]["state"] == "stoppedUP"
    assert "user-stopped" not in qb.forced()


def test_pause_covers_queued_but_not_downloads_or_stopped(make_settings):
    qb, remote, mover = cycle(make_settings())
    paused = {t["hash"] for t in mover.load_paused()}
    assert paused == {"forced", "stalled", "uploading", "queued", "broken"}
    assert remote.mover_starts == 1
    assert qb.torrents["downloading"]["state"] == "downloading"


def test_all_mode_forces_every_torrent_without_a_mover_cycle(make_settings):
    qb = FakeQB(
        [
            torrent("new", "stalledUP"),
            torrent("q", "queuedUP"),
            torrent("done", "forcedUP", True),
            torrent("stopped", "stoppedUP"),
            torrent("dl", "queuedDL"),
        ]
    )
    mover = Mover(make_settings(force_start_mode="all"), qb, FakeRemote())
    assert mover.scheduled()
    assert qb.forced() == {"new", "q", "done", "stopped", "dl"}
    assert qb.forced_calls == [["new", "q", "stopped", "dl"]]


@pytest.mark.parametrize("mode", ["restore", "running"])
def test_other_modes_leave_new_torrents_alone(make_settings, mode):
    qb = FakeQB([torrent("new", "stalledUP"), torrent("q", "queuedUP")])
    assert Mover(make_settings(force_start_mode=mode), qb, FakeRemote()).scheduled()
    assert qb.forced_calls == []


def test_force_pass_waits_while_mover_is_running(make_settings):
    qb, remote, mover = cycle(make_settings(force_start_mode="all"))
    remote.running = True
    assert mover.scheduled()
    assert qb.forced_calls == []
    assert qb.torrents["stalled"]["state"] == "stoppedUP"
    assert mover.load_paused()


def test_resumes_when_paused_too_long(make_settings):
    qb, remote, mover = cycle(make_settings(max_pause_hours=0))
    remote.running = True
    assert mover.scheduled()
    assert not mover.load_paused()
    assert qb.torrents["stalled"]["state"] != "stoppedUP"


def test_resumes_when_nas_is_unreachable(make_settings):
    qb, remote, mover = cycle(make_settings())
    remote.reachable = False
    assert mover.scheduled()
    assert qb.torrents["stalled"]["state"] != "stoppedUP"


def test_pause_does_nothing_when_nas_is_unreachable(make_settings):
    qb = FakeQB(seeded())
    remote = FakeRemote(reachable=False)
    assert not Mover(make_settings(), qb, remote).pause()
    assert qb.torrents["stalled"]["state"] == "stalledUP"
    assert remote.mover_starts == 0


def test_second_pause_keeps_torrents_from_unfinished_run(make_settings):
    qb, _, mover = cycle(make_settings())
    first = {t["hash"]: t["original_state"] for t in mover.load_paused()}
    assert mover.pause()
    assert {t["hash"]: t["original_state"] for t in mover.load_paused()} == first


def test_failed_query_keeps_state_file(make_settings):
    qb, _, mover = cycle(make_settings())
    qb.fail_list = True
    assert not mover.resume()
    assert mover.load_paused()


def test_removed_torrents_are_dropped(make_settings):
    qb, _, mover = cycle(make_settings(), [torrent("a", "stalledUP"), torrent("b", "stalledUP")])
    del qb.torrents["a"]
    assert mover.resume()
    assert not mover.load_paused()


def test_only_unresumed_torrents_are_retried(make_settings):
    qb, _, mover = cycle(make_settings(), [torrent("a", "stalledUP"), torrent("b", "stalledUP")])
    real_resume = qb.resume

    def resume_only_a(hashes):
        return real_resume([h for h in hashes if h == "a"])

    qb.resume = resume_only_a
    assert not mover.resume()
    assert [t["hash"] for t in mover.load_paused()] == ["b"]


def test_reads_state_file_from_previous_version(make_settings):
    settings = make_settings(force_start_mode="restore")
    with open(settings.paused_file, "w") as handle:
        json.dump(
            [{"hash": "a", "name": "a", "original_state": "forcedUP", "paused_at": "2026-11-06T03:00:00"}], handle
        )
    qb = FakeQB([torrent("a", "stoppedUP")])
    assert Mover(settings, qb, FakeRemote(), sleep=lambda _: None).resume()
    assert qb.forced() == {"a"}


@pytest.mark.parametrize(
    "original, mode, expected",
    [
        ({"original_state": "error"}, "all", True),
        ({"original_state": "error"}, "running", False),
        ({"original_state": "queuedUP"}, "running", True),
        ({"original_state": "stalledUP"}, "running", True),
        ({"original_state": "queuedUP"}, "all", True),
        ({"original_state": "stalledUP", "force_start": True}, "restore", True),
    ],
)
def test_wants_force(original, mode, expected):
    assert wants_force(original, mode) is expected


@pytest.mark.parametrize(
    "forced, state, expected",
    [
        (True, "forcedUP", True),
        (True, "stalledUP", False),
        (True, "error", True),
        (False, "stalledUP", True),
        (False, "stoppedUP", False),
        (False, "unknown", False),
    ],
)
def test_resume_state_ok(forced, state, expected):
    assert resume_state_ok(forced, state) is expected
