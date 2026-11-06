#!/bin/sh
# Builds the image and logs in to a real sshd with a passphrase-protected key.
# Usage: tests/integration/test_image.sh [image-tag]
set -eu

IMAGE=${1:-qbt-mover:test}
PREFIX="qbt-mover-it-$$"
NETWORK="$PREFIX-net"
SSHD="$PREFIX-sshd"
APP="$PREFIX-app"
WORK=$(mktemp -d)
# shellcheck disable=SC2016 # literal characters, testing they survive
PASSPHRASE='p@ss w0rd"$with\special'
QBT_PASSWORD_VALUE='qb"pass\word'

cleanup() {
  docker rm -f "$SSHD" "$APP" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok - $*"; }

docker build -q -t "$IMAGE" . >/dev/null
docker network create "$NETWORK" >/dev/null

ssh-keygen -q -t ed25519 -N "$PASSPHRASE" -f "$WORK/key"
chmod 600 "$WORK/key"
docker run -d --name "$SSHD" --network "$NETWORK" -e PUB="$(cat "$WORK/key.pub")" alpine:3.24 sh -c '
  apk add --no-cache openssh >/dev/null && ssh-keygen -A >/dev/null
  sed -i "s/^root:[^:]*:/root:*:/" /etc/shadow
  mkdir -p /root/.ssh && echo "$PUB" > /root/.ssh/authorized_keys && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
  exec /usr/sbin/sshd -D -e' >/dev/null

i=0
until docker exec "$SSHD" sh -c 'pgrep sshd >/dev/null'; do
  i=$((i + 1))
  [ "$i" -lt 60 ] || fail "sshd did not start"
  sleep 1
done
sleep 1

start_app() {
  docker rm -f "$APP" >/dev/null 2>&1 || true
  chmod 600 "$WORK/secrets.env"
  docker run -d --name "$APP" --network "$NETWORK" \
    -e REMOTE_HOST="root@$SSHD" -e QBT_ADDR=http://qbittorrent:8080 -e FORCE_START_MODE=all \
    --tmpfs /run/qbt-mover:mode=0700 --security-opt no-new-privileges:true \
    -v "$WORK/key:/root/.ssh/id_ed25519:ro" \
    -v "$WORK/secrets.env:/run/secrets/qbt_mover:ro" \
    "$IMAGE" >/dev/null
  sleep 2
  [ "$(docker inspect -f '{{.State.Running}}' "$APP")" = true ] || { docker logs "$APP"; fail "container is not running"; }
}

# Correct passphrase
printf 'QBT_LOGIN=admin\nQBT_PASSWORD=%s\nSSH_KEY_PASSPHRASE=%s\n' "$QBT_PASSWORD_VALUE" "$PASSPHRASE" > "$WORK/secrets.env"
start_app
docker logs "$APP" 2>&1 | grep -q "unlocked with the configured passphrase" || { docker logs "$APP"; fail "entrypoint did not unlock the key"; }
pass "entrypoint unlocks the key"
docker exec "$APP" qbt-mover -check-ssh | grep -q "connection OK" || fail "SSH login with passphrase failed"
pass "SSH login works with the passphrase"
docker exec "$APP" qbt-mover -check-ssh >/dev/null || fail "second login failed against the stored host key"
pass "host key stays pinned"

# Secrets handling
[ "$(docker exec "$APP" stat -c %a /run/qbt-mover/qbt.toml)" = 600 ] || fail "qbt.toml is not 600"
[ "$(docker exec "$APP" stat -c %a /run/qbt-mover/ssh_passphrase)" = 600 ] || fail "ssh_passphrase is not 600"
pass "runtime secrets are 600"
docker exec "$APP" python3 -c "
import tomllib
qb = tomllib.load(open('/run/qbt-mover/qbt.toml', 'rb'))['qbittorrent']
assert qb['login'] == 'admin' and qb['password'] == r'''$QBT_PASSWORD_VALUE''', qb
" || fail "special characters in the password were not preserved"
pass "special characters survive into qbt.toml"
if docker exec "$APP" sh -c 'tr "\0" "\n" < /proc/$(pgrep crond)/environ' | grep -qE '^(QBT_PASSWORD|SSH_KEY_PASSPHRASE)='; then
  fail "secret found in the cron environment"
fi
pass "secrets are not in the cron environment"
if docker run --rm --entrypoint sh "$IMAGE" -c 'find /app -name "*.env" -o -name "secrets*" | grep .'; then
  fail "secret-like file baked into the image"
fi
pass "no secret files in the image"
docker exec "$APP" sh -c '. /run/qbt-mover/env; [ "$FORCE_START_MODE" = all ]' || fail "settings not saved for cron"
docker exec "$APP" grep -q "qbt-mover -force-resume-mover" /etc/crontabs/root || fail "crontab not written"
pass "cron has its settings and jobs"

# Wrong passphrase
printf 'SSH_KEY_PASSPHRASE=wrong\n' > "$WORK/secrets.env"
start_app
docker logs "$APP" 2>&1 | grep -q "does not unlock" || fail "wrong passphrase was not reported at startup"
if docker exec "$APP" qbt-mover -check-ssh >/dev/null; then fail "login succeeded with the wrong passphrase"; fi
pass "wrong passphrase is reported and fails"

# No passphrase for a protected key
: > "$WORK/secrets.env"
start_app
docker logs "$APP" 2>&1 | grep -q "not set in secrets.env" || fail "missing passphrase was not reported at startup"
if docker exec "$APP" qbt-mover -check-ssh >/dev/null; then fail "login succeeded without the passphrase"; fi
pass "missing passphrase is reported and fails"

# Container stops cleanly
started=$(date +%s)
docker stop "$APP" >/dev/null
[ $(($(date +%s) - started)) -lt 8 ] || fail "docker stop took too long"
pass "container stops promptly"

echo "All integration checks passed"
