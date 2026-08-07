#!/usr/bin/env bash
set -euo pipefail

APP_ID=4564210
SERVER_INSTALL_DIR="${SERVER_INSTALL_DIR:-/data/server}"
STEAM_PLATFORM_TYPE=windows

STEAM_USERNAME="${STEAM_USERNAME:-}"
STEAM_PASSWORD="${STEAM_PASSWORD:-}"
STEAM_AUTH_CODE="${STEAM_AUTH_CODE:-}"
STEAM_VALIDATE="${STEAM_VALIDATE:-false}"

UPDATE_STAMP="${ACEVO_UPDATE_STAMP:-/data/.last_update}"
AUTO_UPDATE_INTERVAL_HOURS="${AUTO_UPDATE_INTERVAL_HOURS:-12}"

IF_STALE=false
for arg in "$@"; do
  case "${arg}" in
    --if-stale) IF_STALE=true ;;
    *)
      echo "ERROR: unknown argument: ${arg}" >&2
      echo "Usage: update.sh [--if-stale]" >&2
      exit 2
      ;;
  esac
done

# --if-stale is what container start uses: skip entirely while the last successful
# update is recent, so restarting the container does not re-hit Steam every time.
# The dashboard's update button omits the flag and always updates.
if [[ "${IF_STALE}" == "true" && -f "${UPDATE_STAMP}" ]]; then
  interval_seconds=$((AUTO_UPDATE_INTERVAL_HOURS * 3600))
  last_update="$(tr -dc '0-9' < "${UPDATE_STAMP}" | head -c 18)"
  if [[ "${interval_seconds}" -gt 0 && -n "${last_update}" ]]; then
    age=$(($(date +%s) - last_update))
    if [[ "${age}" -ge 0 && "${age}" -lt "${interval_seconds}" ]]; then
      echo "Skipping Steam update: last run was $((age / 60)) min ago (interval ${AUTO_UPDATE_INTERVAL_HOURS}h)."
      exit 0
    fi
  fi
fi

mkdir -p "${SERVER_INSTALL_DIR}"

STEAMCMD_BIN="$(command -v steamcmd || true)"
if [[ -z "${STEAMCMD_BIN}" ]]; then
  echo "ERROR: steamcmd not found in container." >&2
  exit 1
fi

if [[ -z "${STEAM_USERNAME}" ]]; then
  echo "ERROR: STEAM_USERNAME is required." >&2
  echo "Use your Steam account name (not email) for STEAM_USERNAME." >&2
  exit 2
fi

print_hints() {
  local exit_code="$1"

  case "${exit_code}" in
    5)
      echo "Hint: Login denied (password or Steam Guard issue)." >&2
      echo "Use Steam account name (not email) and a fresh STEAM_AUTH_CODE." >&2
      ;;
    8)
      echo "Hint: Missing entitlement/subscription for app ${APP_ID}." >&2
      echo "Owning app 3058630 does not always include dedicated server app ${APP_ID}." >&2
      ;;
  esac
}

fail_with_hints() {
  local exit_code="$1"
  local message="$2"
  echo "ERROR: ${message} (exit code ${exit_code})." >&2
  print_hints "${exit_code}"
  exit "${exit_code}"
}

declare -a app_update_args=(+app_update "${APP_ID}")
if [[ "${STEAM_VALIDATE,,}" == "true" ]]; then
  app_update_args=(+app_update "${APP_ID}" validate)
fi

declare -a base_args=(
  +@sSteamCmdForcePlatformType "${STEAM_PLATFORM_TYPE}"
  +force_install_dir "${SERVER_INSTALL_DIR}"
)

# Prefer the cached token from the Steam volume: a login without a password does
# not trigger a Steam Guard confirmation, so restarts stay tap-free.
run_steamcmd() {
  local -a login_args=("$@")
  set +e
  "${STEAMCMD_BIN}" "${base_args[@]}" "${login_args[@]}" "${app_update_args[@]}" +quit
  local exit_code=$?
  set -e
  return "${exit_code}"
}

echo "SteamCMD login/update phase (cached token) ..."
steamcmd_exit=0
run_steamcmd +login "${STEAM_USERNAME}" || steamcmd_exit=$?

if [[ "${steamcmd_exit}" -ne 0 ]]; then
  if [[ -z "${STEAM_PASSWORD}" ]]; then
    echo "ERROR: cached Steam login failed and STEAM_PASSWORD is not set." >&2
    echo "Set STEAM_PASSWORD once to re-establish the token, then it can be removed again." >&2
    fail_with_hints "${steamcmd_exit}" "SteamCMD login/update failed"
  fi

  echo "Cached token rejected (exit ${steamcmd_exit}); retrying with username/password ..."
  declare -a password_login=(+login "${STEAM_USERNAME}" "${STEAM_PASSWORD}")
  if [[ -n "${STEAM_AUTH_CODE}" ]]; then
    password_login+=("${STEAM_AUTH_CODE}")
  fi

  steamcmd_exit=0
  run_steamcmd "${password_login[@]}" || steamcmd_exit=$?
  if [[ "${steamcmd_exit}" -ne 0 ]]; then
    fail_with_hints "${steamcmd_exit}" "SteamCMD login/update failed"
  fi
fi

# Only a successful run counts, so a failure retries on the next container start.
mkdir -p "$(dirname "${UPDATE_STAMP}")"
date +%s > "${UPDATE_STAMP}"
