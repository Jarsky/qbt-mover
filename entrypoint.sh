#!/bin/sh

# All configuration is handled via environment variables loaded from the .env file (see .env.example)

CONFIG_PATH="/root/.config/qbt/.qbt.toml"

# Add UnRAID host key to known_hosts if not already present
if [ -n "$REMOTE_HOST" ]; then
  HOST=$(echo "$REMOTE_HOST" | cut -d@ -f2)
  if [ -n "$HOST" ] && ! ssh-keygen -F "$HOST" > /dev/null; then
    echo "Scanning and adding SSH host key for $HOST..."
    ssh-keyscan -H "$HOST" >> /root/.ssh/known_hosts 2>/dev/null
  fi
fi

# Create config if it doesn't exist
if [ ! -f "$CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$CONFIG_PATH")"
  cat > "$CONFIG_PATH" <<EOF
[qbittorrent]
addr = "${QBT_ADDR:-http://127.0.0.1:6776}"
login = "${QBT_LOGIN}"
password = "${QBT_PASSWORD}"
EOF
fi

# Set default cron schedules if not provided
CRON_SCHEDULE_PAUSE=${CRON_SCHEDULE_PAUSE:-"0 3 * * *"}
CRON_SCHEDULE_RESUME=${CRON_SCHEDULE_RESUME:-"*/15 * * * *"}

# Ensure config directory exists
mkdir -p /app/config

# Copy default config.ini if not present in mounted volume
if [ ! -f /app/config/config.ini ]; then
  echo "No config.ini found in /app/config, copying default..."
  cp /app/config.ini /app/config/config.ini
else
  echo "config.ini already exists in /app/config, not overwriting."
fi

# Write both cron jobs to root's crontab
# - Pause torrents before mover
# - Resume torrents after mover (waits for mover to finish)
echo "$CRON_SCHEDULE_PAUSE python3 /app/qbt-mover.py -pause" > /etc/crontabs/root
echo "$CRON_SCHEDULE_RESUME python3 /app/qbt-mover.py -force-resume-mover" >> /etc/crontabs/root

echo "Cron jobs set:"
echo "  Pause:  $CRON_SCHEDULE_PAUSE python3 /app/qbt-mover.py -pause"
echo "  Resume: $CRON_SCHEDULE_RESUME python3 /app/qbt-mover.py -force-resume-mover"

# Start cron
crond -f -l 2 &
tail -f /dev/null