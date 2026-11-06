from qbt_mover.cli import acquire_lock, main


def test_unknown_command_shows_usage(make_settings, capsys):
    assert main(["-nope"], make_settings()) == 2
    assert "usage:" in capsys.readouterr().err


def test_lock_is_exclusive(tmp_path):
    path = str(tmp_path / "run.lock")
    held = acquire_lock(path)
    assert acquire_lock(path, blocking=False) is None
    held.close()
    assert acquire_lock(path, blocking=False) is not None


def test_scheduled_job_skips_when_locked(make_settings, capsys):
    settings = make_settings()
    held = acquire_lock(settings.lock_file)
    assert main(["-force-resume-mover"], settings) == 0
    assert "Another run is active" in capsys.readouterr().out
    held.close()
