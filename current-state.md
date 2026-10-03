# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.4.0`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`) + Programmatic API Token (`X-API-Key` header)

## Active Status
- **In-Browser Script Manager (v1.4.0)**:
  - **Storage**: Shell & Python scripts stored in `/data/scripts/` with guaranteed executable permissions (`0755`) and LF normalization.
  - **Browser UI**: Dedicated `📜 Scripts` section with card view, search filter, file size, modification timestamps, permission badges, and cross-referenced job linkages.
  - **Code Editor**: Integrated CodeMirror 5 dark theme with syntax highlighting for Bash and Python, matching brackets, active line highlight, and unsaved changes tracking.
  - **Syntax Validation & Auto-Correction**: Deep validation via `bash -n` and Python AST. Automated 1-click syntax correction for Windows CRLF line endings, unicode smart quotes/dashes, missing shebangs, and trailing whitespace.
  - **Direct Test Execution**: In-browser test runner executes scripts in container subshell with live output streaming, exit code capture, and millisecond execution timing.
  - **Upload & Drag-and-Drop**: Multi-file drag-and-drop zone and upload button supporting `.sh`, `.py`, `.bash`, etc.
  - **Job Drawer Integration**: Script selector helper dropdown in Job creation/edit drawer to insert `/data/scripts/{name}` directly into shell commands.
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
- **Multi-Instance Vaultwarden Sync Active**:
  - **Job #9: Vaultwarden Sync (MTCD <-> Abraham)** (`*/15 * * * *`): Synchronizes logins, TOTP 2FA seeds, and Passkeys (FIDO2 credentials) between `pw.server.mtcd.org` (`tech@mtcd.org`, folder `Sync to Abraham`) and `pw.abraham16.com` (`ben@abraham16.com`, folder `Sync to Abraham`).
  - **Engine**: Dedicated `vw-sync:latest` container (Node.js LTS, `@bitwarden/cli 2026.9.1`, Python 3 dateutil).
  - **Persistence & Isolation**: Separate session cache under `/data/vault-sync/bw-data/{mtcd,abraham}` using `BITWARDENCLI_APPDATA_DIR`.
  - **Config**: `/data/vault-sync/vault-sync.env` (permissions 600).
