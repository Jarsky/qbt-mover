"""The Unraid host, over SSH."""

import os
import subprocess

from .log import logger

CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 30

# Keys are commonly restricted on the Unraid side to these exact command strings.
CMD_CHECK = "echo connected"
CMD_MOVER_RUNNING = "pgrep -f /usr/local/sbin/mover"
CMD_MOVER_START = "nohup mover start >/dev/null 2>&1 &"


class Remote:
    def __init__(self, settings):
        self.host = settings.remote_host
        self.known_hosts = settings.known_hosts_file
        self.passphrase_file = settings.passphrase_file
        self.askpass = settings.askpass

    def _has_passphrase(self):
        try:
            return os.path.getsize(self.passphrase_file) > 0
        except OSError:
            return False

    def _env(self):
        """Hand the key passphrase to ssh through askpass. Without one, never prompt."""
        env = dict(os.environ)
        if self._has_passphrase():
            env.update(SSH_ASKPASS=self.askpass, SSH_ASKPASS_REQUIRE="force")
        else:
            env["SSH_ASKPASS_REQUIRE"] = "never"
        return env

    def _command(self, remote_command):
        return [
            "ssh",
            "-n",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT}",
            # Publickey only, so askpass can never be asked to answer a server password prompt.
            "-o",
            "PreferredAuthentications=publickey",
            "-o",
            "NumberOfPasswordPrompts=1",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            self.host,
            remote_command,
        ]

    def run(self, remote_command):
        try:
            return subprocess.run(
                self._command(remote_command),
                capture_output=True,
                env=self._env(),
                timeout=COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(remote_command, 255, b"", b"timed out")

    def ensure_host_key(self):
        """Trust the host key on first contact, then keep it so a changed key is refused."""
        hostname = self.host.rsplit("@", 1)[-1]
        found = subprocess.run(
            ["ssh-keygen", "-F", hostname, "-f", self.known_hosts],
            capture_output=True,
        )
        if found.returncode == 0:
            return True
        try:
            scan = subprocess.run(
                ["ssh-keyscan", "-H", hostname],
                capture_output=True,
                timeout=COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False
        if not scan.stdout:
            logger.error("Could not read the SSH host key of %s", hostname)
            return False
        with open(self.known_hosts, "ab") as handle:
            handle.write(scan.stdout)
        os.chmod(self.known_hosts, 0o600)
        logger.warning("Trusted new SSH host key for %s; stored in %s", hostname, self.known_hosts)
        return True

    def check(self):
        if not self.host:
            logger.error("remote_host is not set")
            return False
        if not self.ensure_host_key():
            return False
        result = self.run(CMD_CHECK)
        if result.returncode == 0 and b"connected" in result.stdout:
            logger.info("Unraid SSH connection OK: host=%s", self.host)
            return True
        logger.error("Failed to connect to Unraid via SSH: %s", result.stderr.decode(errors="replace").strip())
        return False

    def mover_running(self):
        return bool(self.run(CMD_MOVER_RUNNING).stdout.strip())

    def start_mover(self):
        result = self.run(CMD_MOVER_START)
        if result.returncode == 0:
            logger.info("Mover start status: started")
            return True
        logger.error("Mover start status: failed (%s)", result.stderr.decode(errors="replace").strip())
        return False
