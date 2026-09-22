# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.3.2`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`) + Programmatic API Token (`X-API-Key` header)

## Active Status
- **Authentication**: Authentik SSO OIDC integrated (`auth.abraham16.com`) for web UI users, plus programmatic API token authentication via `X-API-Key` header for `/api/*` endpoints.
- **Host-Operations Toolset**: Container image contains `docker` CLI, `sqlite3`, `rsync`, `openssh-client`, and `tar` to support shell jobs interacting with host containers and remote hosts.
- **Warm Standby HA Sync Automation Active**:
  1. **Job #6: Vaultwarden Backup** (`7 * * * *`): SQLite VACUUM INTO, tar attachments, packages tarball to `/host-backups/vaultwarden/`, and rsyncs to Synology (`/volume1/docker/vaultwarden/backups/`).
  2. **Job #7: Vaultwarden Standby Restore** (`17 * * * *`): Extracts latest backup on Synology to `restore-tmp`, rsyncs non-destructively into `/volume1/docker/vaultwarden-standby/data/` (excluding `icon_cache` and `tmp`), restarts standby container via Portainer API (`/restart?t=2`), and verifies health (`/alive` -> 200).
  3. **Job #8: NPM Config Sync to Synology** (`22 * * * *`): Hourly rsync of `/data` and `/etc/letsencrypt` to `/volume1/docker/nginx-proxy-standby/`, updates sqlite DB and proxy configs for Synology IP, reloads/restarts nginx on standby via Portainer API, and verifies UI responds on port 8081.
- **Multi-Host Docker Cleanups Configured**:
  1. `Docker Containers Cleanup — Abraham Synology` (`30 3 * * *`): Prunes stopped/unused containers on Abraham Synology NAS (Endpoint 5).
  2. `Docker Images Cleanup — Abraham Synology` (`35 3 * * *`): Prunes dangling/unused images on Abraham Synology NAS (Endpoint 5).
  3. `Docker Containers Cleanup — Mac Mini` (`40 3 * * *`): Prunes stopped/unused containers on Ben-Mac-Mini (Endpoint 3).
  4. `Docker Images Cleanup — Mac Mini` (`45 3 * * *`): Prunes dangling/unused images on Ben-Mac-Mini (Endpoint 3).
- **Container**: `benny2168/crondock:1.3.2` running with mounts for `/data`, `/var/run/docker.sock`, `/root/.ssh` (id_ed25519 + known_hosts), `/host-backups`, `/nginx-proxy-src/data`, and `/nginx-proxy-src/letsencrypt`.
- **Validation**: All 7 jobs tested and verified green in production. Standby Vaultwarden (`http://192.168.1.121:5151/alive` -> 200) and NPM (`http://192.168.1.121:8081/` -> 200) confirmed healthy on Synology.
