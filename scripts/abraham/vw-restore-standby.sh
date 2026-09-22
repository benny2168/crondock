#!/bin/bash
# Vaultwarden standby restore script — runs inside CronDock container
set -euo pipefail

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_DIR="/host-backups/vaultwarden"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/restore.log"
PORTAINER_TOK="ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU="
PORTAINER_URL="${PORTAINER_URL:-https://docker.abraham16.com}"
SYNO_HOST="ben@100.91.132.90"
SSH_CMD="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# Stream output to persistent log on disk and stdout/stderr so CronDock captures execution logs
exec 1> >(tee -a "$LOG") 2>&1
echo "[$STAMP] === vw-restore-standby start ==="

# 1. Find latest backup on Synology
LATEST=$($SSH_CMD "$SYNO_HOST" "ls -t /volume1/docker/vaultwarden/backups/vw-*.tgz 2>/dev/null | head -1")
if [ -z "$LATEST" ]; then
  echo "[$STAMP] ERROR: no backups found on Synology"
  exit 1
fi
echo "[$STAMP] Latest backup: $LATEST"

# 2. Extract into staging directory on Synology (restore-tmp is owned by ben)
echo "[$STAMP] Extracting tarball on Synology to restore-tmp..."
$SSH_CMD "$SYNO_HOST" "
  rm -rf /volume1/docker/vaultwarden-standby/restore-tmp && \
  mkdir -p /volume1/docker/vaultwarden-standby/restore-tmp && \
  cd /volume1/docker/vaultwarden-standby/restore-tmp && \
  tar -xzf '$LATEST' db.sqlite3 && \
  tar -xzf '$LATEST' data-files.tgz -O | tar -xz && \
  test -s db.sqlite3
"

# 3. Synchronize staged files into data/ (excluding root-owned runtime dirs icon_cache and tmp)
echo "[$STAMP] Synchronizing data directory on Synology..."
$SSH_CMD "$SYNO_HOST" "
  rsync -a --exclude='icon_cache' --exclude='tmp' /volume1/docker/vaultwarden-standby/restore-tmp/ /volume1/docker/vaultwarden-standby/data/ && \
  rm -f /volume1/docker/vaultwarden-standby/data/db.sqlite3-wal /volume1/docker/vaultwarden-standby/data/db.sqlite3-shm && \
  rm -rf /volume1/docker/vaultwarden-standby/restore-tmp
"

# 4. Restart container to reload database
echo "[$STAMP] Restarting vaultwarden-standby container..."
$SSH_CMD "$SYNO_HOST" "sudo /usr/local/bin/docker restart -t 15 vaultwarden-standby" || \
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOK" \
  "$PORTAINER_URL/api/endpoints/5/docker/containers/vaultwarden-standby/restart?t=15" > /dev/null || true

# 5. Verify health (poll up to 15 times for startup)
echo "[$STAMP] Polling health check..."
HTTP_CODE="000"
for i in {1..15}; do
  sleep 3
  HTTP_CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" http://192.168.1.121:5151/alive || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    break
  fi
done

echo "[$STAMP] Health check HTTP status: $HTTP_CODE"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[$STAMP] ERROR: Health check failed with status $HTTP_CODE"
  exit 1
fi

echo "[$STAMP] === vw-restore-standby complete (healthy) ==="
