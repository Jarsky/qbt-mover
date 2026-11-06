#!/bin/sh
# Cron starts jobs with an almost empty environment, so load the settings the entrypoint saved.
if [ -r /run/qbt-mover/env ]; then
  # shellcheck source=/dev/null
  . /run/qbt-mover/env
fi
cd /app || exit 1
exec python3 -m qbt_mover "$@"
