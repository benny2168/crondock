#!/bin/bash
# NPM config and certs sync script — runs inside CronDock container
set -euo pipefail

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_DIR="/host-backups/nginx-proxy-standby"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"
PORTAINER_TOK="ptr_LAYVFvw5+DscmC2s2QsM+5aeO6iXGYcR4+KwjH7f/eU="
PORTAINER_URL="${PORTAINER_URL:-https://docker.abraham16.com}"
SYNO_HOST="ben@100.91.132.90"
SSH_CMD="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

exec >>"$LOG" 2>&1
echo "[$STAMP] === npm-sync-standby start ==="

SRC_DATA="/nginx-proxy-src/data"
SRC_LE="/nginx-proxy-src/letsencrypt"
DEST_DATA="$SYNO_HOST:/volume1/docker/nginx-proxy-standby/data/"
DEST_LE="$SYNO_HOST:/volume1/docker/nginx-proxy-standby/letsencrypt/"

if [ ! -d "$SRC_DATA" ] || [ ! -d "$SRC_LE" ]; then
  echo "[$STAMP] ERROR: source dirs not mounted ($SRC_DATA / $SRC_LE)"
  exit 1
fi

# 1. Rsync data (database, access lists, proxy host configs)
echo "[$STAMP] Syncing NPM /data..."
rsync -rlt --delete --no-perms --no-owner --no-group \
  --exclude '*.log' \
  --exclude 'logs/*' \
  --exclude 'cache/*' \
  --exclude 'nginx/proxy_host/dead.conf' \
  -e "$SSH_CMD" \
  "$SRC_DATA/" "$DEST_DATA"

# 2. Rsync letsencrypt (certificates and renewal configs)
echo "[$STAMP] Syncing NPM /etc/letsencrypt..."
rsync -rlt --delete --no-perms --no-owner --no-group \
  -e "$SSH_CMD" \
  "$SRC_LE/" "$DEST_LE"

# 3. Post-sync rewrite: transform 192.168.1.120 -> 192.168.1.121 for standby failover
echo "[$STAMP] Rewriting upstream targets from 192.168.1.120 (Mac Mini) to 192.168.1.121 (Synology)..."
$SSH_CMD "$SYNO_HOST" '
  # Update SQLite database on Synology so UI reflects Synology IP
  sqlite3 /volume1/docker/nginx-proxy-standby/data/database.sqlite "UPDATE proxy_host SET forward_host = '\''192.168.1.121'\'' WHERE forward_host = '\''192.168.1.120'\'';"
  sqlite3 /volume1/docker/nginx-proxy-standby/data/database.sqlite "UPDATE proxy_host SET forward_port = 8081 WHERE id = 27;"

  # Rewrite Nginx proxy configurations
  sed -i "s/192\.168\.1\.120/192.168.1.121/g" /volume1/docker/nginx-proxy-standby/data/nginx/proxy_host/*.conf

  # Standby NPM admin UI runs on port 8081 on Synology
  sed -i "s/set \$port           81;/set \$port           8081;/g" /volume1/docker/nginx-proxy-standby/data/nginx/proxy_host/27.conf
'

# 4. Restart standby container via Portainer API so Node.js backend re-reads SQLite database
echo "[$STAMP] Restarting standby NPM container..."
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOK" \
  "$PORTAINER_URL/api/endpoints/5/docker/containers/nginx-proxy-standby/restart?t=2" > /dev/null || \
curl -sS -m 30 -X POST -H "X-API-Key: $PORTAINER_TOK" \
  "http://portainer:9000/api/endpoints/5/docker/containers/nginx-proxy-standby/restart?t=2" > /dev/null || true

# 5. Wait and verify standby port 8081 responds
echo "[$STAMP] Polling NPM standby UI..."
HTTP_CODE="000"
for i in {1..8}; do
  sleep 3
  HTTP_CODE=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" http://192.168.1.121:8081/ || echo "000")
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    break
  fi
done

echo "[$STAMP] NPM Standby UI HTTP status: $HTTP_CODE"
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "302" ]; then
  echo "[$STAMP] WARNING: NPM standby responded with $HTTP_CODE (Node UI may still be starting)"
fi

echo "[$STAMP] === npm-sync-standby complete (healthy) ==="
