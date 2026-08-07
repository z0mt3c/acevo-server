#!/usr/bin/env bash
set -euo pipefail

APP_ID=4564210
SERVER_INSTALL_DIR="${SERVER_INSTALL_DIR:-/data/server}"
STEAM_PLATFORM_TYPE=windows

STEAM_USERNAME="${STEAM_USERNAME:-}"
STEAM_PASSWORD="${STEAM_PASSWORD:-}"
STEAM_AUTH_CODE="${STEAM_AUTH_CODE:-}"
STEAM_VALIDATE="${STEAM_VALIDATE:-false}"

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

# Erst das gecachte Token aus dem Steam-Volume nutzen: ein Login ohne Passwort
# loest keine Steam-Guard-Bestaetigung aus. Da run_server.sh dieses Skript bei
# JEDEM Serverstart aufruft (auch beim Streckenwechsel), waere sonst jedes Mal
# ein Tap in der Mobile-App faellig.
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
