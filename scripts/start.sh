#!/usr/bin/env bash
# Container entrypoint. The dashboard is the long-lived main process: it stays up even when
# the AC EVO server binary crashes, and it starts/stops/restarts the server (scripts/run_server.sh).
set -euo pipefail

PUID="${PUID:-0}"
PGID="${PGID:-0}"

if [[ "${PUID}" -ne 0 && "$(id -u)" -eq 0 ]]; then
  echo "Switching to user PUID=${PUID} and PGID=${PGID}..."

  if ! getent group "${PGID}" > /dev/null; then
    groupadd -g "${PGID}" acevo
  fi
  if ! getent passwd "${PUID}" > /dev/null; then
    useradd -u "${PUID}" -g "${PGID}" -d /root -M -s /bin/bash acevo
  fi

  TARGET_USER="$(getent passwd "${PUID}" | cut -d: -f1)"
  TARGET_GROUP="$(getent group "${PGID}" | cut -d: -f1)"

  # Adjust ownership for required directories
  chown -R "${TARGET_USER}:${TARGET_GROUP}" /data /root /opt/acevo 2>/dev/null || true

  export HOME=/root
  export USER="${TARGET_USER}"
  exec gosu "${TARGET_USER}" "$0" "$@"
fi

mkdir -p /data

# Update on container start only, not on every server start (see run_server.sh).
# --if-stale additionally skips it when the last successful update is still recent.
# A failure must not take the container down: the dashboard stays reachable so the
# problem can be seen in the log and retried via the update button.
if [[ "${AUTO_UPDATE:-true}" =~ ^([Tt]rue|1|[Yy]es|[Oo]n)$ ]]; then
  /opt/acevo/scripts/update.sh --if-stale || echo "WARNING: Steam update failed; starting dashboard anyway." >&2
fi

echo "Starting AC EVO dashboard (container main process) on port ${DASHBOARD_PORT:-8090} ..."
exec python3 -m dashboard
