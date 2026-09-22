# Notes for Next Session — CronDock

## Recently Completed (2026-09-21)
Standby Sync & Restore Resiliency Fixes & CronDock v1.3.2 release:
- **Vaultwarden Standby Restore Script (`scripts/abraham/vw-restore-standby.sh`)**:
  - Replaced atomic directory move with non-destructive staged rsync (`restore-tmp` -> `data/`), avoiding permission conflicts on container-created `root:root` directories like `icon_cache/` and `tmp/`.
  - Replaced stop/start calls with single Portainer restart call (`POST /containers/{id}/restart?t=2`) to comply with Docker 24+ API requirements.
  - Verified end-to-end; standby endpoint `http://192.168.1.121:5151/alive` consistently returns HTTP 200.
- **NPM Standby Config Sync Script (`scripts/abraham/npm-sync-standby.sh`)**:
  - Resolved `127.0.0.1:8999` connection error inside container by routing to `$PORTAINER_URL` (`https://docker.abraham16.com`) with fallback to internal bridge `http://portainer:9000`.
  - Verified SQLite database updates and Nginx proxy configs rewriting to Synology IP `192.168.1.121`.
  - Standby NPM admin UI on `http://192.168.1.121:8081/` verified returning HTTP 200/302.
- **Network Routing Fix**:
  - Fixed Mac Mini intermittent `No route to host` to Synology by disabling secondary Wi-Fi interface `en1` on overlapping `192.168.1.0/24` subnet.
- **CronDock Container Deployed**:
  - Built and deployed `benny2168/crondock:1.3.2`.
  - Health check on `https://cron.abraham16.com/api/health` confirmed live with version `1.3.2`.

## Immediate Backlog
- **Uploadable scripts as a first-class UI feature**: Add UI section under Settings or Jobs for uploading, editing, listing, and deleting shell scripts stored in `/data/scripts/`.
- **Per-job secrets/env vars**: Allow shell jobs to define custom environment variables passed to script execution.
- **Failover Verification Drill**: Document / simulate UDM manual port-forward flip from `192.168.1.140:443` (Mac Mini) to `192.168.1.121:8443` (Synology NPM standby).
- **Push commits**: Push local git commits to `mtcdtech/crondock` remote on `main`.

## Retained Backlog
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
