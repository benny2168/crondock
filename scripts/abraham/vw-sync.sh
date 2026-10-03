#!/bin/bash
# Vaultwarden multi-instance sync runner — runs inside CronDock container
set -euo pipefail

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_DIR="/host-backups/vaultwarden"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"

CTR_ENV="/data/vault-sync/vault-sync.env"
HOST_DATA="/Users/benny2168/Dockers/crondock/data/vault-sync/bw-data"

# Stream output to persistent log and stdout so CronDock captures execution logs
exec 1> >(tee -a "$LOG") 2>&1
echo "[$STAMP] === vw-sync start ==="

if [ ! -f "$CTR_ENV" ]; then
  echo "[$STAMP] ERROR: Configuration file $CTR_ENV does not exist!"
  echo "[$STAMP] Please create it using the template before running this job."
  exit 1
fi

mkdir -p /data/vault-sync/bw-data

# Run the sync container:
# Note: --env-file is read by docker CLI inside crondock (/data/...),
# while -v is resolved by docker daemon on the host (/Users/benny2168/...).
docker run --rm \
  --env-file "$CTR_ENV" \
  -v "$HOST_DATA:/bw-data" \
  vw-sync:latest

echo "[$STAMP] === vw-sync complete ==="
