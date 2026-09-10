# Notes for Next Session — CronDock

## Recently Completed (2026-09-09)
Warm Standby Sync & Restore automation for Vaultwarden and NPM on Abraham Synology:
- **CronDock mounts updated**: Added read-only source mounts `-v /Users/benny2168/Dockers/nginx-proxy-data:/nginx-proxy-src/data:ro` and `-v /Users/benny2168/Dockers/nginx-proxy-letsencrypt:/nginx-proxy-src/letsencrypt:ro` to CronDock container and `docker-compose.yml`.
- **Vaultwarden Standby Restore Script (`/data/scripts/vw-restore-standby.sh`)**:
  - Automatically fetches latest hourly backup (`/volume1/docker/vaultwarden/backups/vw-*.tgz`) on Synology.
  - Extracts database (`db.sqlite3`) and data files/attachments into `.new` directory.
  - Atomically swaps directories on Synology (`mv data data.old`, `mv data.new data`).
  - Restarts `vaultwarden-standby` on Synology via Portainer API (Endpoint 5).
  - Verifies health check on `http://192.168.1.121:5151/alive` (HTTP 200).
  - Scheduled as Job #7 at `17 * * * *` (10 minutes after backup runs at :07).
- **NPM Standby Config Sync Script (`/data/scripts/npm-sync-standby.sh`)**:
  - Rsyncs `/nginx-proxy-src/data/` (excluding logs, cache, dead.conf) to `/volume1/docker/nginx-proxy-standby/data/` on Synology.
  - Rsyncs `/nginx-proxy-src/letsencrypt/` to `/volume1/docker/nginx-proxy-standby/letsencrypt/` on Synology.
  - Reloads Nginx on standby container via Portainer exec API (`nginx -s reload`).
  - Verifies UI responsiveness on `http://192.168.1.121:8081/` (HTTP 200).
  - Scheduled as Job #8 at `22 * * * *`.
- **Acceptance Tests**: All 7 jobs active and verified green. Standby Vaultwarden DB size (3.02MB) and certificates matched primary.

## Immediate Backlog
- **Uploadable scripts as a first-class UI feature**: Add UI section under Settings or Jobs for uploading, editing, listing, and deleting shell scripts stored in `/data/scripts/`.
- **Per-job secrets/env vars**: Allow shell jobs to define custom environment variables passed to script execution.
- **Failover Verification Drill**: Document / simulate UDM manual port-forward flip from `192.168.1.140:443` (Mac Mini) to `192.168.1.121:8443` (Synology NPM standby).
- **Push commits**: Push local git commits to `mtcdtech/crondock` remote on `main`.

## Retained Backlog
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
