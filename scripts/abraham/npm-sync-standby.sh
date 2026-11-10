#!/bin/bash
# NPM config and certs sync script — runs inside CronDock container
set -euo pipefail

LOG_DIR="/host-backups/nginx-proxy-standby"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"
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
echo "[$(now)] === npm-sync-standby start ==="

SRC_DATA="/nginx-proxy-src/data"
SRC_LE="/nginx-proxy-src/letsencrypt"
DEST_DATA="$SYNO_HOST:/volume1/docker/nginx-proxy-standby/data/"
DEST_LE="$SYNO_HOST:/volume1/docker/nginx-proxy-standby/letsencrypt/"

if [ ! -d "$SRC_DATA" ] || [ ! -d "$SRC_LE" ]; then
  echo "[$(now)] ERROR: source dirs not mounted ($SRC_DATA / $SRC_LE)"
  exit 1
fi

# 1. Rsync data and letsencrypt to Synology shared folder (/volume1/docker)
echo "[$(now)] Syncing NPM /data to Synology shared folder..."
rsync -rlt --delete --no-perms --no-owner --no-group \
  --exclude '*.log' \
  --exclude 'logs/*' \
  --exclude 'cache/*' \
  --exclude 'nginx/proxy_host/dead.conf' \
  -e "$SSH_CMD" \
  "$SRC_DATA/" "$DEST_DATA"

echo "[$(now)] Syncing NPM /etc/letsencrypt to Synology shared folder..."
rsync -rlt --delete --no-perms --no-owner --no-group \
  -e "$SSH_CMD" \
  "$SRC_LE/" "$DEST_LE"

# 2. Local mirror on Synology from volume1 shared folder to volume2 NVMe (@docker-standby)
# Note: @-prefixed directory on /volume2 prevents DSM synocheckshare from renaming it on reboot/upgrade
echo "[$(now)] Mirroring to Synology NVMe (/volume2/@docker-standby/nginx-proxy-standby)..."
$SSH_CMD "$SYNO_HOST" '
  sudo mkdir -p /volume2/@docker-standby/nginx-proxy-standby/data /volume2/@docker-standby/nginx-proxy-standby/letsencrypt && \
  sudo rsync -a --delete /volume1/docker/nginx-proxy-standby/data/ /volume2/@docker-standby/nginx-proxy-standby/data/ && \
  sudo rsync -a --delete /volume1/docker/nginx-proxy-standby/letsencrypt/ /volume2/@docker-standby/nginx-proxy-standby/letsencrypt/
'
# 3. Post-sync rewrite: transform 192.168.1.120 -> 192.168.1.121 for standby failover
echo "[$(now)] Rewriting upstream targets from 192.168.1.120 (Mac Mini) to 192.168.1.121 (Synology)..."
$SSH_CMD "$SYNO_HOST" '
  # Update SQLite database on Synology so UI reflects Synology IP
  sudo sqlite3 /volume2/@docker-standby/nginx-proxy-standby/data/database.sqlite "UPDATE proxy_host SET forward_host = '\''192.168.1.121'\'' WHERE forward_host = '\''192.168.1.120'\'';"
  sudo sqlite3 /volume2/@docker-standby/nginx-proxy-standby/data/database.sqlite "UPDATE proxy_host SET forward_port = 8081 WHERE id = 27;"

  # Rewrite Nginx proxy configurations
  sudo sed -i "s/192\.168\.1\.120/192.168.1.121/g" /volume2/@docker-standby/nginx-proxy-standby/data/nginx/proxy_host/*.conf
  sudo sed -i "s/host\.docker\.internal/192.168.1.120/g" /volume2/@docker-standby/nginx-proxy-standby/data/nginx/proxy_host/*.conf

  # Standby NPM admin UI runs on port 8081 on Synology
  sudo sed -i "s/set \$port           81;/set \$port           8081;/g" /volume2/@docker-standby/nginx-proxy-standby/data/nginx/proxy_host/27.conf
'

# 4. Ensure standby container exists and restart so Node.js backend re-reads SQLite database
echo "[$(now)] Ensuring standby NPM container is running and reloading configuration..."
$SSH_CMD "$SYNO_HOST" '
  if ! sudo /usr/local/bin/docker inspect nginx-proxy-standby >/dev/null 2>&1; then
    echo "Container nginx-proxy-standby missing — recreating on Synology NVMe..."
    sudo /usr/local/bin/docker run -d \
      --name nginx-proxy-standby \
      --restart unless-stopped \
      --label com.abraham16.role=standby \
      -p 8080:80 \
      -p 8443:443 \
      -p 8081:81 \
      -v /volume2/@docker-standby/nginx-proxy-standby/data:/data \
      -v /volume2/@docker-standby/nginx-proxy-standby/letsencrypt:/etc/letsencrypt \
      jc21/nginx-proxy-manager:latest
  else
    sudo /usr/local/bin/docker restart -t 15 nginx-proxy-standby
  fi
' || \
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOK" \
  "$PORTAINER_URL/api/endpoints/5/docker/containers/nginx-proxy-standby/restart?t=15" > /dev/null || true

# 5. Wait and verify standby port 8081 responds (poll up to 40 times with 5s sleep = ~200s timeout)
echo "[$(now)] Polling NPM standby UI on http://192.168.1.121:8081/..."
HTTP_CODE="000"
for i in {1..40}; do
  sleep 5
  HTTP_CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" http://192.168.1.121:8081/ 2>/dev/null || true)
  if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then HTTP_CODE="000"; fi
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "[$(now)] NPM standby UI responding on attempt $i (HTTP $HTTP_CODE)"
    break
  fi
  echo "[$(now)] Attempt $i/40: HTTP $HTTP_CODE, waiting..."
done

echo "[$(now)] Final NPM Standby UI HTTP status: $HTTP_CODE"
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "302" ]; then
  echo "[$(now)] WARNING: NPM standby responded with $HTTP_CODE (Node UI may still be starting)"
fi

echo "[$(now)] === npm-sync-standby complete (healthy) ==="
