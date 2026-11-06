from qbt_mover import remote as remote_module
from qbt_mover.remote import CMD_CHECK, CMD_MOVER_RUNNING, CMD_MOVER_START, Remote


def test_remote_commands_stay_exact_for_restricted_keys():
    # authorized_keys rules on the Unraid side can match these strings literally
    assert CMD_CHECK == "echo connected"
    assert CMD_MOVER_RUNNING == "pgrep -f /usr/local/sbin/mover"
    assert CMD_MOVER_START == "nohup mover start >/dev/null 2>&1 &"


def test_no_passphrase_never_prompts(make_settings):
    env = Remote(make_settings())._env()
    assert env["SSH_ASKPASS_REQUIRE"] == "never"
    assert "SSH_ASKPASS" not in env or env["SSH_ASKPASS"] != make_settings().askpass


def test_empty_passphrase_file_counts_as_none(make_settings):
    settings = make_settings()
    open(settings.passphrase_file, "w").close()
    assert Remote(settings)._env()["SSH_ASKPASS_REQUIRE"] == "never"


def test_passphrase_uses_askpass_and_stays_off_the_command_line(make_settings):
    settings = make_settings()
    with open(settings.passphrase_file, "w") as handle:
        handle.write("s3cret\n")
    remote = Remote(settings)
    env = remote._env()
    assert env["SSH_ASKPASS"] == settings.askpass
    assert env["SSH_ASKPASS_REQUIRE"] == "force"
    assert "s3cret" not in " ".join(remote._command(CMD_CHECK))


def test_ssh_only_offers_publickey_and_pins_host_key(make_settings):
    settings = make_settings()
    command = Remote(settings)._command(CMD_CHECK)
    assert "PreferredAuthentications=publickey" in command
    assert "StrictHostKeyChecking=yes" in command
    assert f"UserKnownHostsFile={settings.known_hosts_file}" in command
    assert command[-2:] == ["root@tower", CMD_CHECK]


def test_timeout_is_a_failure_not_a_crash(make_settings, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise remote_module.subprocess.TimeoutExpired("ssh", 1)

    monkeypatch.setattr(remote_module.subprocess, "run", raise_timeout)
    assert Remote(make_settings()).run(CMD_CHECK).returncode == 255


def test_check_fails_without_remote_host(make_settings):
    assert Remote(make_settings(remote_host="")).check() is False
