#!/bin/sh
set -eu

: "${ARCHIVE_KEY:?ARCHIVE_KEY is required}"
mkdir -p /tmp/radar
umask 077
printf '%s' "$ARCHIVE_KEY" | gpg --quiet --batch --yes --pinentry-mode loopback \
  --passphrase-fd 0 --decrypt --output /tmp/radar/payload.tgz /app/.assets/node.dat
tar -xzf /tmp/radar/payload.tgz -C /tmp/radar
cd /tmp/radar
exec python -m uvicorn webhook:app --host 0.0.0.0 --port "${PORT:-10000}"
