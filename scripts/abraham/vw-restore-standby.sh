#!/bin/bash
# Vaultwarden warm-standby restore.
# Invoked hourly by CronDock job #7 (schedule: "17 * * * *").
#
# 1. Find newest vw-*.tgz backup on Abraham Synology (produced by job #6)
# 2. Extract to /volume1/docker/vaultwarden-standby/data.new
# 3. Stop vaultwarden-standby container via Portainer API
# 4. Atomic swap: data -> data.old, data.new -> data
# 5. Start container
# 6. Delete data.old, verify /alive endpoint
set -euo pipefail

# ── Config from env ─────────────────────────────────────────────────────────
: "${PORTAINER_URL:?PORTAINER_URL not set}"
: "${PORTAINER_TOKEN:?PORTAINER_TOKEN not set}"
: "${PORTAINER_ENDPOINT_ID:?PORTAINER_ENDPOINT_ID not set}"
: "${STANDBY_HOST:?STANDBY_HOST not set}"
: "${STANDBY_SSH_USER:?STANDBY_SSH_USER not set}"

# ── Constants ───────────────────────────────────────────────────────────────
CONTAINER=vaultwarden-standby
DATA_DIR=/volume1/docker/vaultwarden-standby/data
BACKUP_GLOB=/volume1/docker/vaultwarden/backups/vw-*.tgz
HEALTH_URL=http://192.168.1.121:5151/alive
LOG_DIR=/host-backups/vaultwarden
LOG=$LOG_DIR/restore.log
SSH="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o BatchMode=yes ${STANDBY_SSH_USER}@${STANDBY_HOST}"

mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "[$STAMP] === vw-restore-standby start ==="

# 1. Find latest backup
LATEST=$($SSH "ls -t $BACKUP_GLOB 2>/dev/null | head -1")
if [ -z "$LATEST" ]; then
  echo "[$STAMP] ERROR: no backup tarballs found on $STANDBY_HOST"
  exit 1
fi
echo "[$STAMP] Latest backup: $LATEST"

# 2. Extract to .new
$SSH "rm -rf ${DATA_DIR}.new && mkdir -p ${DATA_DIR}.new && cd ${DATA_DIR}.new && tar -xzf '$LATEST' --strip-components=1 && test -s db.sqlite3"
echo "[$STAMP] Extracted to ${DATA_DIR}.new"

# 3. Stop container via Portainer
echo "[$STAMP] Stopping $CONTAINER..."
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOKEN" \
  "${PORTAINER_URL}/api/endpoints/${PORTAINER_ENDPOINT_ID}/docker/containers/${CONTAINER}/stop?t=10" \
  > /dev/null || true

# 4. Atomic swap
$SSH "cd $(dirname $DATA_DIR) && rm -rf $(basename $DATA_DIR).old && ([ -d $(basename $DATA_DIR) ] && mv $(basename $DATA_DIR) $(basename $DATA_DIR).old || true) && mv $(basename $DATA_DIR).new $(basename $DATA_DIR)"
echo "[$STAMP] Swapped directories"

# 5. Start container
echo "[$STAMP] Starting $CONTAINER..."
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOKEN" \
  "${PORTAINER_URL}/api/endpoints/${PORTAINER_ENDPOINT_ID}/docker/containers/${CONTAINER}/start" \
  > /dev/null

# 6. Cleanup + verify
sleep 3
$SSH "rm -rf ${DATA_DIR}.old"

sleep 5
CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")
if [ "$CODE" = "200" ]; then
  echo "[$STAMP] Health check OK (HTTP $CODE)"
else
  echo "[$STAMP] WARNING: health check returned HTTP $CODE"
  exit 1
fi

echo "[$STAMP] === vw-restore-standby end ==="
