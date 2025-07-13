![qBt-mover](https://github.com/Jarsky/qbt-mover/blob/main/qBT-mover_logo.jpg)

# qBt-mover

qBt-mover is a Dockerized automation tool for coordinating qBittorrent and UnRAID's mover process. It uses the actively maintained `ludviglundgren/qbittorrent-cli` to manage torrents via the qBittorrent Web API, and SSH to control the UnRAID mover.

## Why?

qBittorrent locks files that are active. If you're using the Cache in UnRAID, when the daily mover runs to move files to the array, seeding torrents can prevent the mover from moving them. This tool automatically pauses torrents before the mover runs, starts the mover, and then resumes torrents once the mover is finished.

## Features
- Pauses only torrents that need to be paused, and resumes only those paused by the script
- Integrates with UnRAID's mover via SSH (fully detached, non-blocking)
- Robust logging to both Docker logs and persistent log files
- All configuration and logs are persisted via Docker volumes
- Fully unattended operation, designed for cron scheduling via environment variables

## Installation & Setup

### Prerequisites
- Docker & docker-compose

> **Note:** All other dependencies, including [qBittorrent CLI (ludviglundgren/qbittorrent-cli)](https://github.com/ludviglundgren/qbittorrent-cli) and jq (JSON processor), are installed automatically as part of the Docker build. You do not need to install them on your host system.

### 1. Generate and configure SSH keys
Generate an SSH key if you don't have one:
```bash
ssh-keygen -t rsa -b 4096 -C "your_email@domain.com"
```
Copy your public key to UnRAID (run on your host):
```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub root@tower
```
Test passwordless SSH:
```bash
ssh root@tower
```
If you are not prompted for a password, setup is correct.

### 2. Environment Configuration
Copy the example environment file and edit it to match your environment:
```bash
cp .env.example .env
nano .env
```
All configuration—including qBittorrent connection settings, UnRAID host, and cron schedules—is handled via the `.env` file. See `.env.example` for all available options.

### 3. Docker Compose Setup
Update your `docker-compose.yml` to mount config and SSH keys, and use the `.env` file:
```yaml
services:
  qbt-mover:
    build: .
    container_name: qbt-mover
    volumes:
      - ./.data/config:/app/config
      - ./.data/logs:/app/logs
      - ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro
      - ~/.ssh/id_rsa.pub:/root/.ssh/id_rsa.pub:ro
    networks:
      - mediabox
    env_file:
      - .env
    restart: unless-stopped
networks:
  mediabox:
    external: true
```

Build and run the container:
```bash
docker-compose build
docker-compose up -d
```

## Usage

All scheduling is handled via cron jobs inside the container, controlled by environment variables in your `.env` file:
- `CRON_SCHEDULE_PAUSE`: When to pause torrents (e.g., before the UnRAID mover runs)
- `CRON_SCHEDULE_RESUME`: How often to check if the mover is finished and resume torrents

**Example:**
- Pause at 3:00 AM:
  ```env
  CRON_SCHEDULE_PAUSE=0 3 * * *
  ```
- Check every 15 minutes for mover completion and resume:
  ```env
  CRON_SCHEDULE_RESUME=*/15 * * * *
  ```

The pause job only needs to run once before the mover starts. The resume job can run frequently; the script will only resume torrents once the mover is finished, so it is safe to run every 15 minutes or at your preferred interval. Adjust these times to match your UnRAID mover schedule and your needs.

## Logging

- Logs are written to both `/app/logs/qbt-mover.log` (persistent, via Docker volume) and to stdout (visible with `docker logs <container>`).
- No need to manually configure logrotate; manage log retention via your Docker volume or external log management.

## Security Note
- Never commit your private key to version control or bake it into a Docker image.
- Always mount your SSH key as a volume or use Docker secrets for production.

## Troubleshooting
- Ensure your SSH key permissions are correct and the container can access them.
- Check Docker logs for real-time script output: `docker logs <container>`
- Check `/app/logs/qbt-mover.log` for persistent logs.
- Make sure your `.env` file is correct and accessible in the project root.

## Migrating from Legacy Scripts
- All previous manual script usage (`qbt-mover.sh`, `qbt-pause.sh`, etc.) is deprecated.
- All operations are now handled by the Dockerized Python script and scheduled via environment variables.
- No need to manually set up cron jobs or run scripts by hand.
