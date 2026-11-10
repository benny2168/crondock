#!/bin/bash
# Vaultwarden multi-instance sync runner — runs inside CronDock container
set -euo pipefail

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_DIR="/host-backups/vaultwarden"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"

if [ -f "/data/scripts/vault-sync.env" ]; then
  CTR_ENV="/data/scripts/vault-sync.env"
elif [ -f "/data/vault-sync/vault-sync.env" ]; then
  CTR_ENV="/data/vault-sync/vault-sync.env"
else
  echo "[$STAMP] ERROR: Configuration file not found in /data/scripts/ or /data/vault-sync/!"
  exit 1
fi

HOST_DATA="/Users/benny2168/Dockers/crondock/data/vault-sync/bw-data"

# Stream output to persistent log and stdout so CronDock captures execution logs
exec 1> >(tee -a "$LOG") 2>&1
echo "[$STAMP] === vw-sync start ==="
echo "[$STAMP] Using config: $CTR_ENV"

mkdir -p /data/vault-sync/bw-data

# Auto-build vw-sync:latest if pruned or missing locally
if ! docker image inspect vw-sync:latest >/dev/null 2>&1; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Image vw-sync:latest not found locally — building from /data/vault-sync..."
  docker build -t vw-sync:latest /data/vault-sync
fi

# Run the sync container:
docker run --rm \
  --env-file "$CTR_ENV" \
  -v "$HOST_DATA:/bw-data" \
  vw-sync:latest

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === vw-sync complete ==="
