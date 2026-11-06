#!/bin/sh
# Prepare secrets and settings in a private runtime directory, then run cron.
set -eu
umask 077

RUNTIME_DIR=/run/qbt-mover
SECRETS_FILE=/run/secrets/qbt_mover
CONFIG_FILE=/app/config/config.ini

mkdir -p "$RUNTIME_DIR" /app/config /app/logs /root/.ssh
chmod 700 "$RUNTIME_DIR" /root/.ssh

info() { echo "[entrypoint] $*"; }
warn() { echo "[entrypoint] WARNING: $*"; }

# Print a value from the secrets file. Parsed as literal text, never executed by the shell.
secret_value() {
  [ -f "$SECRETS_FILE" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "$1="*)
        printf '%s' "${line#*=}"
        return 0
        ;;
    esac
  done < "$SECRETS_FILE"
}

# Print a credential from the secrets file, falling back to the environment.
credential() {
  value=$(secret_value "$1")
  if [ -z "$value" ]; then
    eval "value=\${$1:-}"
    if [ -n "$value" ] && [ "$1" != QBT_LOGIN ]; then
      warn "$1 is set in the environment, where docker inspect shows it; move it to secrets.env" >&2
    fi
  fi
  printf '%s' "$value"
}

if [ -f "$SECRETS_FILE" ]; then
  case "$(stat -c %a "$SECRETS_FILE")" in
    400|600) ;;
    *) warn "secrets.env is readable by group or others on the host; run: chmod 600 secrets.env" ;;
  esac
fi

toml_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
shell_quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

# qBittorrent connection
qbt_login=$(credential QBT_LOGIN)
qbt_password=$(credential QBT_PASSWORD)
cat > "$RUNTIME_DIR/qbt.toml" <<TOML
[qbittorrent]
addr = "$(toml_escape "${QBT_ADDR:-http://qbittorrent:8080}")"
login = "$(toml_escape "$qbt_login")"
password = "$(toml_escape "$qbt_password")"
TOML
unset qbt_login qbt_password QBT_LOGIN QBT_PASSWORD

# SSH key passphrase
passphrase=$(credential SSH_KEY_PASSPHRASE)
rm -f "$RUNTIME_DIR/ssh_passphrase"
if [ -n "$passphrase" ]; then
  printf '%s\n' "$passphrase" > "$RUNTIME_DIR/ssh_passphrase"
fi
unset passphrase SSH_KEY_PASSPHRASE

# Report key problems now rather than at the next scheduled pause
found_key=false
for key in /root/.ssh/id_*; do
  case "$key" in
    *.pub) continue ;;
    */id_\*) continue ;;
  esac
  found_key=true
  case "$(stat -c %a "$key")" in
    400|600) ;;
    *) warn "$key must be chmod 600 on the host; ssh will refuse to use it" ;;
  esac
  if SSH_ASKPASS_REQUIRE=never ssh-keygen -y -P "" -f "$key" >/dev/null 2>&1; then
    warn "$key has no passphrase"
  elif [ ! -s "$RUNTIME_DIR/ssh_passphrase" ]; then
    warn "$key has a passphrase but SSH_KEY_PASSPHRASE is not set in secrets.env; SSH will fail"
  elif ! SSH_ASKPASS=/usr/local/libexec/qbt-mover-askpass SSH_ASKPASS_REQUIRE=force \
      ssh-keygen -y -f "$key" </dev/null >/dev/null 2>&1; then
    warn "SSH_KEY_PASSPHRASE in secrets.env does not unlock $key; SSH will fail"
  else
    info "$key unlocked with the configured passphrase"
  fi
done
if [ "$found_key" = false ]; then
  warn "no SSH key mounted in /root/.ssh"
fi

# Default config on first run
if [ ! -f "$CONFIG_FILE" ]; then
  info "No config.ini found, copying the default"
  cp /app/defaults/config.ini "$CONFIG_FILE"
fi

# Save non-secret settings for cron jobs
: > "$RUNTIME_DIR/env"
for name in REMOTE_HOST FORCE_START_MODE MAX_PAUSE_HOURS TZ; do
  eval "value=\${$name:-}"
  if [ -n "$value" ]; then
    printf 'export %s=%s\n' "$name" "$(shell_quote "$value")" >> "$RUNTIME_DIR/env"
  fi
done

CRON_SCHEDULE_PAUSE=${CRON_SCHEDULE_PAUSE:-0 3 * * *}
CRON_SCHEDULE_RESUME=${CRON_SCHEDULE_RESUME:-*/15 * * * *}
cat > /etc/crontabs/root <<CRON
$CRON_SCHEDULE_PAUSE qbt-mover -pause >> /proc/1/fd/1 2>&1
$CRON_SCHEDULE_RESUME qbt-mover -force-resume-mover >> /proc/1/fd/1 2>&1
CRON
info "Pause schedule:  $CRON_SCHEDULE_PAUSE"
info "Resume schedule: $CRON_SCHEDULE_RESUME"
info "Force-start mode: ${FORCE_START_MODE:-from config.ini or restore}"

# dcron can't run as PID 1 (setpgid fails), so stay as the parent and forward stop signals.
crond -f -l 2 &
crond_pid=$!
trap 'kill "$crond_pid" 2>/dev/null' TERM INT
wait "$crond_pid" || true
