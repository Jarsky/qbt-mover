<p align="center"><img src="docs/assets/logo.jpg" alt="qBt-mover logo" width="480"></p>

# qBt-mover

[![CI](https://github.com/Jarsky/qbt-mover/actions/workflows/ci.yml/badge.svg)](https://github.com/Jarsky/qbt-mover/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![qBittorrent](https://img.shields.io/badge/qBittorrent-5.3.0%20tested-2F67BA?logo=qbittorrent&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/Jarsky/qbt-mover)](https://github.com/Jarsky/qbt-mover/commits/main)

qBittorrent holds the files of active torrents open, and Unraid's mover skips open files, so seeding torrents can stay on the cache indefinitely. qBt-mover pauses those torrents, runs the mover over SSH, and resumes them when it finishes.

## Features

- Pauses only the torrents that could block the mover and resumes only the ones it paused.
- Three [force-start modes](#force-start-modes).
- Resumes anyway if the NAS is unreachable or the mover runs too long, so seeding doesn't get stuck.
- SSH keys with passphrases, with [all credentials in one file](#credentials).
- Pins the Unraid host key after first contact and refuses a changed key.

## Setup

You need Docker with Compose, a qBittorrent Web UI the container can reach, and SSH access to Unraid. Everything else is in the image.

**1. Get the project and create your config files**

```bash
git clone https://github.com/Jarsky/qbt-mover.git
cd qbt-mover
cp .env.example .env
cp secrets.env.example secrets.env
chmod 600 secrets.env
```

**2. Create an SSH key and authorize it on Unraid**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/qbt-mover_ed25519
ssh-copy-id -i ~/.ssh/qbt-mover_ed25519.pub root@tower
```

**3. Fill in your settings**

- `secrets.env`: your qBittorrent login and the key's passphrase.
- `.env`: `QBT_ADDR`, `REMOTE_HOST`, `SSH_KEY_PATH`, `DOCKER_NETWORK` and your schedules.

**4. Start it and test the connection**

```bash
docker compose up -d --build
docker compose logs qbt-mover
docker exec qbt-mover qbt-mover -check-ssh
```

The startup log reports a missing or wrong passphrase, or a key with unsafe permissions.

## Credentials

Credentials live in `secrets.env`, which git and Docker builds both ignore:

```ini
QBT_LOGIN=admin
QBT_PASSWORD=your password
SSH_KEY_PASSPHRASE=your passphrase
```

Values are read literally up to the end of the line, so special characters are fine and quotes aren't needed.

- Compose mounts the file read-only as a secret, so its values don't appear in `docker inspect`. Credentials set in `.env` still work, but they do appear there and the container warns about it.
- At startup the container copies what it needs into a private, memory-only directory with `600` permissions.
- SSH gets the passphrase through `SSH_ASKPASS`, so it never appears on a command line. SSH is limited to publickey authentication, so the passphrase can't be sent to a server as a password.

The passphrase has to be stored for unattended runs. It protects the key if the key file is copied elsewhere, but not if someone can read both files, so keep `secrets.env` at `600`.

If the Unraid host key legitimately changes, delete `.data/config/known_hosts` and restart. The new key is trusted on next contact.

## Force-start modes

Set `FORCE_START_MODE` in `.env`:

| Mode | What gets force-started | When |
|---|---|---|
| `restore` (default) | Only torrents that were force-started before the pause | On resume |
| `running` | Every torrent the pause stopped: running, forced or queued | On resume |
| `all` | Every torrent in qBittorrent | On resume and every scheduled run |

`all` is for keeping everything seeding, so it has real side effects:

- It starts torrents you stopped yourself, so they won't stay stopped.
- It force-starts downloads too, which ignores qBittorrent's download and queue limits.
- It waits while torrents are paused for the mover, so it won't interfere with a mover run.

Modes only turn force-start on. Changing to a lower mode doesn't undo it on torrents that are already forced.

## Configuration

Settings in `.env` take priority over `.data/config/config.ini`, which is created on first run.

| `.env` | `config.ini` | Default | Purpose |
|---|---|---|---|
| `QBT_ADDR` | | `http://qbittorrent:8080` | qBittorrent Web UI address |
| `REMOTE_HOST` | `remote_host` | | SSH target, such as `root@tower` |
| `SSH_KEY_PATH` | | `~/.ssh/id_ed25519` | Private key on the Docker host |
| `DOCKER_NETWORK` | | Required | Existing Docker network that can reach qBittorrent |
| `TZ` | | `UTC` | Time zone for schedules and logs |
| `CRON_SCHEDULE_PAUSE` | | `0 3 * * *` | When to pause and start the mover |
| `CRON_SCHEDULE_RESUME` | | `*/15 * * * *` | How often to check for the mover finishing |
| `FORCE_START_MODE` | `force_start_mode` | `restore` | See [force-start modes](#force-start-modes) |
| `MAX_PAUSE_HOURS` | `max_pause_hours` | `4` | Resume after this long even if the mover is still running |
| | `states` | `forcedUP, stalledUP, uploading, queuedUP, error` | States paused before the mover runs |

## Commands

Run these with `docker exec qbt-mover qbt-mover <command>`:

| Command | What it does |
|---|---|
| `-check-ssh` | Tests the SSH connection, including the passphrase |
| `-pause` | Pauses torrents and starts the mover |
| `-force-resume-mover` | Resumes if the mover has finished, then applies the force-start mode (the scheduled job) |
| `-resume` | Resumes paused torrents now, without checking the mover |
| `-force-start` | Runs the force-start pass now (`all` mode only) |

## Restricting the SSH key

The key only needs these three commands on Unraid, so you can limit it there. In `authorized_keys`, use a `command=` rule pointing at a script that checks `$SSH_ORIGINAL_COMMAND` against this list and runs only exact matches:

```
echo connected
pgrep -f /usr/local/sbin/mover
nohup mover start >/dev/null 2>&1 &
```

## Logs

View logs with `docker logs qbt-mover`. They're also written to `.data/logs/qbt-mover.log`, which rotates at 10 MB and keeps three old files. New log files are readable by root only.

## Upgrading from 1.x

1. Create `secrets.env` as in [setup](#setup) and move `QBT_LOGIN` and `QBT_PASSWORD` into it from `.env`.
2. Set `SSH_KEY_PATH` and `DOCKER_NETWORK` in `.env`, and `FORCE_START_MODE` if you want something other than `restore`.
3. Add `queuedUP` to `states` in `.data/config/config.ini`. An existing file keeps its old list, so queued torrents wouldn't be paused otherwise.
4. Run `docker compose up -d --build`.

`config.ini` and any torrents still paused carry over. Images built by 1.x copied `.env` into the image, so remove old images if they contained a password.

## Development

```bash
pip install pytest ruff
pytest
ruff check . && ruff format --check .
tests/integration/test_image.sh    # needs Docker
```

```
src/qbt_mover/   application code
docker/          entrypoint and container helper scripts
config/          default config.ini
tests/           unit tests, plus an image test against a real sshd
legacy/          the old Bash version, for reference
```

## License

[MIT](LICENSE)
