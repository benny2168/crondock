#!/bin/bash
# Vaultwarden standby restore script — runs inside CronDock container
set -euo pipefail

LOG_DIR="/host-backups/vaultwarden"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/restore.log"
PORTAINER_TOK="ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU="
PORTAINER_URL="${PORTAINER_URL:-https://docker.abraham16.com}"
SYNO_HOST="ben@100.91.132.90"
SSH_CMD="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# Helper for current timestamp
now() {
  date '+%Y-%m-%d %H:%M:%S'
}

# Stream output to persistent log on disk and stdout/stderr so CronDock captures execution logs
exec 1> >(tee -a "$LOG") 2>&1
echo "[$(now)] === vw-restore-standby start ==="

# 1. Find latest backup on Synology
LATEST=$($SSH_CMD "$SYNO_HOST" "ls -t /volume1/docker/vaultwarden/backups/vw-*.tgz 2>/dev/null | head -1")
if [ -z "$LATEST" ]; then
  echo "[$(now)] ERROR: no backups found on Synology"
  exit 1
fi
echo "[$(now)] Latest backup: $LATEST"

# 2. Extract into staging directory on Synology NVMe (/volume2/@docker-standby)
# Note: @-prefixed directory on /volume2 prevents DSM synocheckshare from renaming it on reboot/upgrade
NVME_VW_DIR="/volume2/@docker-standby/vaultwarden-standby"
echo "[$(now)] Extracting tarball on Synology to ${NVME_VW_DIR}/restore-tmp..."
$SSH_CMD "$SYNO_HOST" "
  sudo mkdir -p '${NVME_VW_DIR}/data' '${NVME_VW_DIR}/restore-tmp' && \
  sudo chown -R ben:users '${NVME_VW_DIR}' && \
  rm -rf '${NVME_VW_DIR}/restore-tmp' && \
  mkdir -p '${NVME_VW_DIR}/restore-tmp' && \
  cd '${NVME_VW_DIR}/restore-tmp' && \
  tar -xzf '$LATEST' db.sqlite3 && \
  tar -xzf '$LATEST' data-files.tgz -O | tar -xz && \
  test -s db.sqlite3
"

# 3. Synchronize staged files into data/ on NVMe (excluding root-owned runtime dirs icon_cache and tmp)
echo "[$(now)] Synchronizing data directory on Synology NVMe (${NVME_VW_DIR}/data)..."
$SSH_CMD "$SYNO_HOST" "
  sudo rsync -a --exclude='icon_cache' --exclude='tmp' '${NVME_VW_DIR}/restore-tmp/' '${NVME_VW_DIR}/data/' && \
  sudo rm -f '${NVME_VW_DIR}/data/db.sqlite3-wal' '${NVME_VW_DIR}/data/db.sqlite3-shm' && \
  rm -rf '${NVME_VW_DIR}/restore-tmp'
"

# 4. Ensure vaultwarden-standby container exists and restart to reload database
echo "[$(now)] Ensuring vaultwarden-standby container is running and reloading database..."
$SSH_CMD "$SYNO_HOST" '
  if ! sudo /usr/local/bin/docker inspect vaultwarden-standby >/dev/null 2>&1; then
    echo "Container vaultwarden-standby missing — recreating on Synology NVMe..."
    sudo /usr/local/bin/docker run -d \
      --name vaultwarden-standby \
      --restart unless-stopped \
      --label com.abraham16.role=standby \
      -p 5151:80 \
      -p 3012:3012 \
      -v /volume2/@docker-standby/vaultwarden-standby/data:/data:rw \
      -e ROCKET_PORT=80 \
      -e ROCKET_ADDRESS=0.0.0.0 \
      -e ROCKET_PROFILE=release \
      -e DOMAIN=https://pw.abraham16.com \
      -e '\''ADMIN_TOKEN=$argon2id$v=19$m=65540,t=3,p=4$sCDZmpfjK/CHK3cR+i28v8bObTxnqQLU+pD2HRIW5lI$2Uv6x8v8dVpLfgpO7pLX57r4AANHzHaGIJA62gnZ7wI'\'' \
      -e SSO_ENABLED=true \
      -e SSO_ONLY=false \
      -e SSO_AUTHORITY=https://auth.abraham16.com/application/o/vaultwarden/ \
      -e SSO_CLIENT_ID=s3rln_MomD4XaFNGPMar2RNPf2bysTXN \
      -e SSO_CLIENT_SECRET=9mPFd7mZR1n9zDB1TXgdoy-E1hJzo2agXlQ_5FL49J6UAbUwLKu8LA4NVx9D9CAfYfOUzDHpCx3Tzu6taNlf_w \
      -e '\''SSO_SCOPES=openid profile email'\'' \
      -e SSO_PKCE=true \
      -e SSO_SIGNUPS_MATCH_EMAIL=true \
      vaultwarden/server:latest
  else
    sudo /usr/local/bin/docker restart -t 15 vaultwarden-standby
  fi
' || \
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOK" \
  "$PORTAINER_URL/api/endpoints/5/docker/containers/vaultwarden-standby/restart?t=15" > /dev/null || true

# 5. Verify health (poll up to 40 times with 5s sleep = ~200s timeout)
echo "[$(now)] Polling health check on http://192.168.1.121:5151/alive..."
HTTP_CODE="000"
for i in {1..40}; do
  sleep 5
  HTTP_CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" http://192.168.1.121:5151/alive || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "[$(now)] Health check passed on attempt $i (HTTP 200)"
    break
  fi
  echo "[$(now)] Attempt $i/40: HTTP $HTTP_CODE, waiting..."
done

echo "[$(now)] Final health check HTTP status: $HTTP_CODE"
if [ "$HTTP_CODE" != "200" ]; then
  echo "[$(now)] ERROR: Health check failed with status $HTTP_CODE after 40 attempts"
  exit 1
fi

echo "[$(now)] === vw-restore-standby complete (healthy) ==="
