# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.3.3`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`) + Programmatic API Token (`X-API-Key` header)

## Active Status
- **Authentication**: Authentik SSO OIDC integrated (`auth.abraham16.com`) for web UI users, plus programmatic API token authentication via `X-API-Key` header for `/api/*` endpoints.
- **Host-Operations Toolset**: Container image contains `docker` CLI, `sqlite3`, `rsync`, `openssh-client`, and `tar` to support shell jobs interacting with host containers and remote hosts.
- **Database Concurrency**: SQLite configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `PRAGMA synchronous=NORMAL`, and 30-second busy timeout to eliminate write contention across threads.
- **Warm Standby HA Sync Automation Active**:
  1. **Job #6: Vaultwarden Backup** (`7 * * * *`): SQLite VACUUM INTO, tar attachments, packages tarball to `/host-backups/vaultwarden/`, and rsyncs to Synology (`/volume1/docker/vaultwarden/backups/`).
  2. **Job #7: Vaultwarden Standby Restore** (`17 * * * *`): Extracts latest backup on Synology to `restore-tmp`, rsyncs non-destructively into `/volume1/docker/vaultwarden-standby/data/` (excluding `icon_cache` and `tmp`), restarts standby container via direct SSH (`docker restart -t 15`), and verifies health (`/alive` -> 200). Verified operational (`success=1`, full streamed logs).
  3. **Job #8: NPM Config Sync to Synology** (`22 * * * *`): Hourly rsync of `/data` and `/etc/letsencrypt` to `/volume1/docker/nginx-proxy-standby/`, updates sqlite DB and proxy configs for Synology IP (including `host.docker.internal` -> LAN IP rewrite), restarts standby container, and verifies UI responds on port 8081. Verified operational (`success=1`, full streamed logs).
- **Execution Log Streaming**: Both `vw-restore-standby.sh` and `npm-sync-standby.sh` stream output via `tee` so stdout/stderr are saved in CronDock's database, eliminating `(no output)` in the UI.
- **Multi-Host Docker Cleanups Active**:
  1. `Docker Containers Cleanup — Abraham Synology` (`30 3 * * *`): Prunes stopped/unused containers on Abraham Synology NAS (Endpoint 5).
  2. `Docker Images Cleanup — Abraham Synology` (`35 3 * * *`): Prunes dangling/unused images on Abraham Synology NAS (Endpoint 5).
  3. `Docker Containers Cleanup — Mac Mini` (`40 3 * * *`): Prunes stopped/unused containers on Ben-Mac-Mini (Endpoint 3) — **Enabled & Verified**.
  4. `Docker Images Cleanup — Mac Mini` (`45 3 * * *`): Prunes dangling/unused images on Ben-Mac-Mini (Endpoint 3) — **Enabled & Verified**.
- **Container**: `benny2168/crondock:1.3.3` running with mounts for `/data`, `/var/run/docker.sock`, `/root/.ssh` (id_ed25519 + known_hosts), `/host-backups`, `/nginx-proxy-src/data`, and `/nginx-proxy-src/letsencrypt`.
- **Validation**: All 7 jobs tested, enabled, and verified green (`last_run_success = 1`) in production.
