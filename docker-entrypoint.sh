#!/bin/sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

mkdir -p /data/tts-cache /config/voices /config/imaging

if [ "$(id -u)" = "0" ]; then
  chown -R "$PUID:$PGID" /data /config 2>/dev/null || true
  exec gosu "$PUID:$PGID" "$@"
fi

exec "$@"
