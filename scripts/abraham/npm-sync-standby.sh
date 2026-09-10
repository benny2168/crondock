#!/bin/bash
# Nginx Proxy Manager warm-standby sync.
# Invoked hourly by CronDock job #8 (schedule: "22 * * * *").
#
# Rsyncs primary NPM data + letsencrypt dirs from Ben-Mac-Mini
# (read-only mounts inside CronDock) to Abraham Synology standby.
set -euo pipefail

# ── Config from env ─────────────────────────────────────────────────────────
: "${STANDBY_HOST:?STANDBY_HOST not set}"
: "${STANDBY_SSH_USER:?STANDBY_SSH_USER not set}"

# ── Constants ───────────────────────────────────────────────────────────────
SRC_DATA=/nginx-proxy-src/data
SRC_LE=/nginx-proxy-src/letsencrypt
DEST_DATA=${STANDBY_SSH_USER}@${STANDBY_HOST}:/volume1/docker/nginx-proxy-standby/data/
DEST_LE=${STANDBY_SSH_USER}@${STANDBY_HOST}:/volume1/docker/nginx-proxy-standby/letsencrypt/
LOG_DIR=/host-backups/nginx-proxy-standby
LOG=$LOG_DIR/sync.log
RSYNC_SSH="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o BatchMode=yes"

mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1

STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "[$STAMP] === npm-sync-standby start ==="

if [ ! -d "$SRC_DATA" ] || [ ! -d "$SRC_LE" ]; then
  echo "[$STAMP] ERROR: source mounts missing."
  echo "  Expected: $SRC_DATA and $SRC_LE"
  echo "  Recreate CronDock container with these bind mounts:"
  echo "    -v /Users/benny2168/Dockers/nginx-proxy-data:/nginx-proxy-src/data:ro"
  echo "    -v /Users/benny2168/Dockers/nginx-proxy-letsencrypt:/nginx-proxy-src/letsencrypt:ro"
  exit 1
fi

# Sync /data — exclude logs and cache (large, regenerable)
echo "[$STAMP] Syncing /data..."
rsync -a --delete \
  --exclude 'logs/' \
  --exclude '*.log' \
  --exclude 'cache/' \
  --exclude 'nginx/proxy_host/dead.conf' \
  -e "$RSYNC_SSH" \
  "$SRC_DATA/" "$DEST_DATA"

# Sync letsencrypt (certs) — no excludes
echo "[$STAMP] Syncing /letsencrypt..."
rsync -a --delete \
  -e "$RSYNC_SSH" \
  "$SRC_LE/" "$DEST_LE"

echo "[$STAMP] === npm-sync-standby end ==="
