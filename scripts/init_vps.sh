#!/usr/bin/env sh
set -eu

HOST_UID=$(id -u)
HOST_GID=$(id -g)
ENV_FILE=.env
TMP_FILE="${ENV_FILE}.tmp"

if [ -f "$ENV_FILE" ]; then
  grep -v '^BLOODLINES_UID=' "$ENV_FILE" \
    | grep -v '^BLOODLINES_GID=' > "$TMP_FILE" || true
else
  cp .env.example "$TMP_FILE"
  grep -v '^BLOODLINES_UID=' "$TMP_FILE" \
    | grep -v '^BLOODLINES_GID=' > "${TMP_FILE}.clean" || true
  mv "${TMP_FILE}.clean" "$TMP_FILE"
fi

{
  echo "BLOODLINES_UID=${HOST_UID}"
  echo "BLOODLINES_GID=${HOST_GID}"
  cat "$TMP_FILE"
} > "$ENV_FILE"
rm -f "$TMP_FILE"

mkdir -p data/input data/output data/telegram deploy/proxy

if [ ! -w data/input ] || [ ! -w data/output ] || [ ! -w data/telegram ]; then
  echo "VPS initialization failed: ./data must be writable by the current user." >&2
  echo "Current user: $(id -un) (${HOST_UID}:${HOST_GID})" >&2
  echo "Fix checkout ownership, for example:" >&2
  echo "  sudo chown -R $(id -un):$(id -gn) $(pwd)" >&2
  exit 1
fi

echo "Historical Bloodlines VPS environment initialized"
echo "Host user: $(id -un) (${HOST_UID}:${HOST_GID})"
echo "Compose environment: $(pwd)/.env"
echo "Existing Telegram/proxy settings were preserved."
