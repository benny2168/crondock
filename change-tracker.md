# Change Tracker — CronDock

### 2026-10-03 — v1.4.0: In-Browser Script Manager with Syntax Correction
- **Feature**: Implemented full in-browser script management enabling users to upload, view, edit (with automated syntax correction), test-run, and save shell and Python scripts directly from the CronDock web interface.
- **Backend Implementation**:
  1. `app/scripts_manager.py`: Modular script operations engine supporting safe filename sanitization (preventing directory traversal / shell injection), reading/writing to `/data/scripts/`, setting `0755` executable permissions, and normalizing CRLF to Unix LF.
  2. **Deep Syntax Validation**:
     - Bash scripts verified via `bash -n` in a non-executing subshell, parsing line numbers, error descriptions, and providing contextual guidance hints (e.g., missing `then`, unbalanced loops, unclosed quotes).
     - Python scripts verified via `ast.parse()`, capturing syntax errors with line, column, and code snippets.
     - Detects Windows CRLF line endings (`\r\n`) and Unicode smart/curly typography quotes (`“”‘’—`).
  3. **Automated 1-Click Syntax Correction**:
     - Automatically cleans CRLF to LF.
     - Replaces Unicode curly/smart quotes with standard ASCII equivalents.
     - Adds proper shebang (`#!/usr/bin/env bash` or `#!/usr/bin/env python3`) if missing.
     - Trims trailing whitespace.
  4. **Subshell Test Runner**: `POST /api/scripts/{filename}/test-run` executes scripts in container subshell with output streaming, exit code capture, and millisecond duration measurement.
  5. **API Endpoints**: Full REST suite for listing scripts, reading, creating, uploading (multipart `UploadFile`), updating, deleting, checking syntax, and test running.
- **Frontend Implementation**:
  1. **Scripts Navigation & Card View**: Dedicated `📜 Scripts` section showing cards with script language icon, file size, timestamps, permission badges, and cross-referenced linkages to active jobs using each script.
  2. **CodeMirror 5 Editor**: Vendored local CodeMirror 5 dark theme with syntax highlighting, matching brackets, active line highlighting, unsaved changes tracking, and keyboard shortcuts (`Ctrl/Cmd+S` to save, `Ctrl/Cmd+Shift+F` to auto-fix).
  3. **Multi-File Drag & Drop & Upload**: Visual drop zone for dropping scripts directly into the browser.
  4. **Live Syntax Status Bar**: Visual indicator showing green/amber/red syntax state with clickable error pills that jump straight to the offending line in the editor.
  5. **Job Drawer Integration**: Added script selector dropdown in the Job creation/edit drawer to insert `/data/scripts/{name}` directly into shell commands with 1-click jump to edit.
- **Validation**:
  - Python files compiled cleanly with 0 syntax errors.
  - JavaScript syntax verified with `node -c app/static/app.js`.
  - Built Docker image `benny2168/crondock:1.4.0` and `latest`.
  - Recreated local container via `docker compose up -d`.
  - Health check `GET /api/health` verified returning `{"ok":true,"version":"1.4.0"}`.
  - Tested `GET /api/scripts` returning all 4 existing scripts with correct job links.
  - Tested `POST /api/scripts/check-syntax` with valid, invalid, and smart-quote/CRLF scripts with 1-click auto-fix verified.
  - Tested `POST /api/scripts`, multipart upload `/api/scripts/upload`, `test-run`, and `DELETE`.
  - Verified all static web assets return HTTP 200 OK.

### 2026-09-21 — v1.3.4: Vaultwarden Standby Restore & CronDock Log Output Streaming
- **Issues**:
  1. Vaultwarden Standby Restore (Job #7) showed failed in CronDock.
  2. All execution log history in CronDock UI displayed `(no output)` when clicking into job runs.
- **Root Causes**:
  1. **`(no output)` in Job Logs**: Both `vw-restore-standby.sh` and `npm-sync-standby.sh` used `exec >>"$LOG" 2>&1`, which redirected all stdout and stderr exclusively into `/host-backups/.../*.log`. As a result, CronDock's subprocess runner captured an empty string (`""`), causing the UI to display `(no output)` across all historic runs in `job_logs`.
  2. **Vaultwarden Standby Failures & Restarts**:
     - Synology's ContainerManager Docker daemon had encountered bridge network corruption (`heartbeat_default`/`heartbeat_net`), causing dockerd socket communication timeouts.
     - The container restart command used `curl ... /restart?t=2` via the external Portainer API. Under Synology BTRFS I/O load, Vaultwarden required ~13s to cleanly flush SQLite and exit. The 2-second timeout (`t=2`) triggered a SIGKILL, and Docker 24.0.2 on Synology flagged the container as manually stopped (`ShouldRestart failed ... error="restart canceled" hasBeenManuallyStopped=true`), leaving the container in `Exited` state.
     - With the container stopped, the 8-iteration health check loop timed out and logged `ERROR: Health check failed with status 000`.
  3. **NPM Standby Configuration**: Syncing configurations from Mac Mini introduced `host.docker.internal` (used for AGStack proxy host 29 on Mac Mini), which failed DNS resolution on Synology Linux and caused Nginx startup failures.
- **Fixes**:
  1. Updated logging redirection in `vw-restore-standby.sh` and `npm-sync-standby.sh` to `exec 1> >(tee -a "$LOG") 2>&1` so execution output streams simultaneously to disk and stdout/stderr for CronDock's database capture.
  2. Recovered Synology `pkg-ContainerManager-dockerd.service` and recreated `vaultwarden-standby` on standard bridge network (`-p 5151:80 -p 3012:3012`).
  3. Replaced fragile `t=2` Portainer restart with direct SSH host command `$SSH_CMD "$SYNO_HOST" "sudo /usr/local/bin/docker restart -t 15 ..."` (with Portainer fallback), and expanded health check polling to 15 iterations (45s).
  4. Added upstream rewrite rule `sed -i "s/host\.docker\.internal/192.168.1.120/g"` in `npm-sync-standby.sh` to rewrite Mac Mini container hosts to the LAN IP on Synology.
  5. Synchronized scripts to live CronDock data directory `/Users/benny2168/Dockers/crondock/data/scripts/`.
- **Validation**:
  - Triggered Job #7 (`vw-restore-standby.sh`) via CronDock API: Job 1010 completed with exit code 0 (`success=1`), output 714 bytes streamed, and health check returned HTTP 200 (`"2026-09-22T04:52:13.309910"`).
  - Triggered Job #8 (`npm-sync-standby.sh`) via CronDock API: Job 1011 completed with exit code 0 (`success=1`), output 1738 bytes streamed.
  - All 7 active CronDock jobs verified enabled and `last_run_success = 1`.


### 2026-09-21 — v1.3.3: SQLite Concurrency Hardening (WAL Mode) & Mac Mini Tasks Re-enabled
- **Issue**: Attempting to re-enable Job #4 ("Docker Containers Cleanup — Mac Mini") or Job #5 ("Docker Images Cleanup — Mac Mini") from the UI or API failed with `500 Internal Server Error` caused by `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked` on `UPDATE jobs SET enabled=?, updated_at=? WHERE jobs.id = ?`.
- **Root Cause**: The SQLite database was operating in default `delete` rollback-journal mode on a host Docker bind mount without a busy timeout. Concurrent reads from `AuthMiddleware` / API token checks and background scheduler sessions locked the entire file, causing writes to timeout after SQLite's default 5-second window.
- **Fix**:
  1. Updated `app/database.py` with `connect_args={"check_same_thread": False, "timeout": 30}`.
  2. Added SQLAlchemy `connect` event listener to enforce `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, and `PRAGMA busy_timeout=30000`.
  3. Rebuilt container `benny2168/crondock:1.3.3` and deployed.
  4. Both Mac Mini tasks (Job #4 and Job #5) were re-enabled. Manual test runs verified successful HTTP 200 execution against Portainer Mac Mini Endpoint 3.
- **Validation**:
  - `PUT /api/jobs/4` and `PUT /api/jobs/5` toggle sub-20ms without lock errors.
  - Test run of Job #4 returned HTTP 200 in 68ms.
  - Test run of Job #5 returned HTTP 200.
  - Health check `https://cron.abraham16.com/api/health` returns `{"ok":true,"version":"1.3.3"}`.

### 2026-09-21 — v1.3.2: Standby Sync & Restore Resiliency Fixes (Vaultwarden + NPM)
- **Change**: Resolved failure states in automated hourly standby restore for Vaultwarden (Job #7) and config sync for Nginx Proxy Manager (Job #8). Bumped CronDock to `v1.3.2`.
- **Root Causes & Fixes**:
  1. **Job #7 (Vaultwarden Standby Restore)**:
     - *Issue*: Atomic directory rename (`mv data data.old`) failed on Synology because `icon_cache/` was created by the Docker container with `root:root` ownership and `700` permissions, which the non-root SSH user `ben` could not move or delete (`rm: cannot remove ... Permission denied`). Subsequent runs tried to move `data.new` into an existing `data/` directory, failing with `Directory not empty`.
     - *Fix*: Rewrote `scripts/abraham/vw-restore-standby.sh` to extract the archive to a staging directory (`restore-tmp` owned by `ben`), sync files non-destructively into `/volume1/docker/vaultwarden-standby/data/` using `rsync -a --exclude='icon_cache' --exclude='tmp'`, delete stale WAL/SHM locks, and clean up staging.
     - *Container Restart*: Switched container restart from separate stop/start to Portainer API `POST /containers/{id}/restart?t=2` (avoids Docker 24+ 400 Bad Request error when body is passed to `/start`).
  2. **Job #8 (NPM Standby Config Sync)**:
     - *Issue*: Script failed with `curl: (7) Failed to connect to 127.0.0.1:8999` because port 8999 was an OrbStack host port on Mac Mini, not exposed or accessible inside the container network namespace.
     - *Fix*: Updated `scripts/abraham/npm-sync-standby.sh` to target `$PORTAINER_URL` (`https://docker.abraham16.com`), with fallback to `http://portainer:9000` (Docker internal bridge DNS).
  3. **Mac Mini Dual-Interface Routing Conflict**:
     - *Issue*: Mac Mini had both `en0` (10GbE Ethernet) and `en1` (Wi-Fi) connected to the same subnet (`192.168.1.0/24`). macOS kernel routing flagged `192.168.1.121` on `en1` as blackholed (`!`), causing intermittent `No route to host` errors when communicating with Synology.
     - *Fix*: Disabled Wi-Fi interface via `networksetup -setairportpower en1 off`.
- **Validation**:
  - `vw-restore-standby.sh` ran inside CronDock container and exited with code 0 (`vw-restore-standby complete (healthy)`). Synology endpoint `http://192.168.1.121:5151/alive` returned HTTP 200.
  - `npm-sync-standby.sh` ran inside CronDock container and exited with code 0 (`npm-sync-standby complete (healthy)`). Synology endpoint `http://192.168.1.121:8081/` returned HTTP 200.
  - `crondock:1.3.2` container built, deployed, and verified: `https://cron.abraham16.com/api/health` returns `{"ok":true,"version":"1.3.2"}`.

### 2026-09-09 — Warm Standby HA Sync Automation Deployed (Vaultwarden + NPM)
- **Change**: Configured and deployed automated hourly warm-standby synchronization and restoration for Vaultwarden and Nginx Proxy Manager (NPM) from Ben-Mac-Mini to Abraham Synology NAS (`192.168.1.121` / `100.91.132.90`) to provide instant disaster recovery in case OrbStack/Mac-Mini goes down.
- **Actions**:
  1. Recreated `crondock` container on Mac Mini with read-only source mounts for `/Users/benny2168/Dockers/nginx-proxy-data:/nginx-proxy-src/data:ro` and `/Users/benny2168/Dockers/nginx-proxy-letsencrypt:/nginx-proxy-src/letsencrypt:ro`.
  2. Created `/data/scripts/vw-restore-standby.sh` inside CronDock data volume: automates hourly extraction of the latest Vaultwarden backup archive on Synology, atomic directory swap to `/volume1/docker/vaultwarden-standby/data`, container restart via Portainer API, and health verification.
  3. Created `/data/scripts/npm-sync-standby.sh` inside CronDock data volume: automates hourly rsync of NPM configuration, SQLite database, and Let's Encrypt certificates to `/volume1/docker/nginx-proxy-standby/`, followed by Nginx reload via Portainer container exec API.
  4. Created CronDock Job #7 (`Vaultwarden Standby Restore` at `17 * * * *`) and Job #8 (`NPM Config Sync to Synology` at `22 * * * *`) via CronDock REST API.
  5. Updated `docker-compose.yml` volumes to persist all host mounts.
- **Validation**:
  - `vw-restore-standby.sh` triggered and verified end-to-end; restored 3.02MB database; Synology endpoint `http://192.168.1.121:5151/alive` returned HTTP 200.
  - `npm-sync-standby.sh` triggered and verified end-to-end; 204.8KB database and SSL live certificates synced; Synology UI `http://192.168.1.121:8081/` returned HTTP 200.
  - All 7 active CronDock jobs verified operational.


## 2026-09-09 — Abraham fork created (branch `abraham`)

**What:** Forked mtcdtech/crondock to benny2168/crondock. Created `abraham`
branch as permanent divergence for Abraham-network-specific config and
warm-standby automation.

**Why:** Abraham deployment is growing responsibilities (warm-standby sync
to Synology) that don't belong in the shared upstream. Fork lets Abraham
diverge without polluting mtcdtech/main; upstream fixes still pullable via
`git fetch mtcdtech && git merge mtcdtech/main`.

**Added:**
- `docker-compose.abraham.yml` — env-var-driven compose with `.env.abraham`
- `.env.abraham.example` — template of required env vars
- `scripts/abraham/vw-restore-standby.sh` — hourly VW restore
- `scripts/abraham/npm-sync-standby.sh` — hourly NPM config sync
- `docs/abraham/warm-standby.md` — topology, failover, rollback
- `docs/abraham/deployment.md` — Abraham deployment guide
- `.gitignore` — added `.env.abraham` block

**Not changed:**
- `docker-compose.yml` — still the active Abraham config (until deploy of
  new compose file, tracked in notes-next-session.md)
- `app/`, `Dockerfile`, `requirements.txt` — track upstream unchanged
- `docker-compose.mtcd.yml` — MTCD config, untouched

**Version:** No app version bump (this is repo restructuring).
**Deployed:** No — Phase 2 handoff work (recreate container with new mounts,
create CronDock jobs #7 and #8) is separate. See notes-next-session.md.

### 2026-09-08 — v1.3.1: Host-Operations Toolset for Shell Jobs
- **Change**: Added host-operation and remote-sync CLI utilities (`docker-cli`, `sqlite`, `openssh-client`, `rsync`, `tar`) to the CronDock container image to enable shell jobs that interact with host Docker containers and remote hosts (e.g. Vaultwarden hourly backup and remote NAS sync).
- **Actions**:
  1. Updated `Dockerfile` runtime packages (`apk add --no-cache curl tzdata bash docker-cli sqlite openssh-client rsync tar`).
  2. Bumped `APP_VERSION` to `1.3.1` in `app/main.py` and updated UI version subtitle to `v1.3.1` in `app/static/index.html`.
  3. Built local Docker image `benny2168/crondock:1.3.1` and `benny2168/crondock:latest` targeting `linux/arm64`.
- **Validation**:
  - Verified tool presence and executability in image via `which docker sqlite3 rsync ssh tar`.
  - Verified CLI versions (`docker --version`, `sqlite3 --version`, `rsync --version`, `ssh -V`).
  - Deploy-first test mode: container runtime verification pending parent orchestrator container recreation with host mounts.

### 2026-09-08 — v1.3.0: API Token Authentication for Programmatic Access
- **Change**: Added API token authentication support (`X-API-Key` header) for all `/api/*` endpoints, allowing external scripts, automated workflows, and secondary orchestrators to manage jobs and settings programmatically without requiring interactive Authentik SSO.
- **Actions**:
  1. Added `verify_api_key(token: str) -> bool` in `app/auth.py` using constant-time comparison (`secrets.compare_digest`) against the `API_KEY` setting in the SQLite database.
  2. Updated `AuthMiddleware.dispatch` in `app/main.py` to inspect `X-API-Key` on `/api/*` requests before evaluating session cookies, populating `request.state.user = {"api": True, "name": "api-token"}` on success. Missing/invalid tokens fall through to existing SSO authentication.
  3. Seeded `API_KEY` setting in `app/database.py` with `is_secret=True` and default empty value (opt-in; empty token disables API header authentication).
  4. Bumped `APP_VERSION` to `1.3.0` in `app/main.py` and updated UI version subtitle in `app/static/index.html`.
- **Validation**:
  - Python compile and module imports validated locally (`py_compile` and `import main; import auth`).
  - Unit tests executed via Docker verifying empty token rejection, disabled setting behavior, invalid token 401 response, and valid token authentication.
  - Local Docker image `benny2168/crondock:1.3.0` (and `latest`) built for native ARM64 on Ben-Mac-Mini.
  - Deploy-first validation pending production rollout to Portainer stack at `cron.abraham16.com`.

### 2026-09-07 — v1.2.0: HTTP Execution Resilience, Retry Backoff & Duration Tracking
- **Change**: Enhanced HTTP execution resilience against timeouts and transient network/daemon errors, added JSON pretty-formatting, added execution duration tracking in logs, and shifted Abraham Docker image cleanup off the 3:00 AM DSM maintenance window to 3:30 AM (`30 3 * * *`).
- **Actions**:
  1. Updated `app/scheduler.py` with 300s default timeout (configurable via `HTTP_TIMEOUT` setting) and a 3-attempt retry loop with exponential backoff on transient errors (timeouts, connect drops, 502/503/504, 409).
  2. Implemented `_format_http_body` in `app/scheduler.py` to auto-format JSON responses with clean indentation.
  3. Added `duration_ms` property on `JobLog` (`app/database.py`) and field in `JobLogResponse` (`app/models.py`).
  4. Updated `app/static/app.js` and `app/static/index.html` to display formatted runtime duration (`⏱ 1.2s`), human-friendly status labels (`HTTP 200`, `Timeout / Error`), and updated logo subtitle to `v1.2.0`.
  5. Updated database default schedule for Abraham Docker Cleanup to `30 3 * * *`.
  6. Bumped `APP_VERSION` to `1.2.0` across `app/main.py` and `app/static/index.html`.
- **Validation**:
  - Python compilation validated with zero syntax/type errors.
  - Image `benny2168/crondock:1.2.0` built and deployed to Ben-Mac-Mini.
  - Production `/api/health` confirmed returning `{"ok": true, "version": "1.2.0"}`.

### 2026-09-07 — v1.1.0: Migration from Synology SSO to Authentik & UI Updates
- **Change**: Migrated Abraham CronDock instance (`cron.abraham16.com`) authentication from legacy DSM Synology SSO to Authentik OIDC (`auth.abraham16.com`), bumped version to `1.1.0`, and updated login branding.
- **Actions**:
  1. Created OAuth2 provider `crondock` (confidential, PK 6) and application `CronDock` in Authentik (`auth.abraham16.com`).
  2. Configured redirect URI `https://cron.abraham16.com/auth/callback`.
  3. Updated `docker-compose.yml` with `AUTH_PROVIDER=oidc`, `LOGIN_PROVIDER_NAME=Authentik SSO`, and new Client ID / Secret.
  4. Updated login page button and icon to "Sign in with Authentik SSO" (`app/static/login.html`).
  5. Updated application version to `1.1.0` in `app/main.py` (`FastAPI` app & `/api/health`) and `app/static/index.html`.
  6. Built image `benny2168/crondock:1.1.0` on Ben-Mac-Mini and deployed container via Portainer Docker API.
- **Validation**:
  - OpenID discovery endpoint verified at `https://auth.abraham16.com/application/o/crondock/.well-known/openid-configuration`.
  - Production health endpoint `https://cron.abraham16.com/api/health` confirmed returning `{"ok": true, "version": "1.1.0"}`.
  - Login page `https://cron.abraham16.com/login` confirmed rendering "Sign in with Authentik SSO".
  - Auth start endpoint `https://cron.abraham16.com/auth/start` verified returning HTTP 302 redirect to `https://auth.abraham16.com/application/o/authorize/`.

### 2026-10-03 — Multi-Instance Vaultwarden Sync (MTCD <-> Abraham)
- **Change**: Built and deployed a synchronization engine between Church (`pw.server.mtcd.org`) and Personal (`pw.abraham16.com`) Vaultwarden instances, preserving TOTP seeds and Passkeys (FIDO2 credentials).
- **Actions**:
  1. Created `scripts/vault-sync/sync.py` implementing isolated CLI sessions via `BITWARDENCLI_APPDATA_DIR`, folder discovery/auto-creation, `_sync_uuid` item binding, payload sanitization preserving `login.totp` and `login.fido2Credentials`, and timestamp-based conflict resolution (`revisionDate`).
  2. Created `scripts/vault-sync/Dockerfile` packaging Node.js LTS, `@bitwarden/cli 2026.9.1`, and Python 3.
  3. Built local Docker image `vw-sync:latest` on Apple Silicon ARM64.
  4. Created CronDock runner script `scripts/abraham/vw-sync.sh` and deployed to `/Users/benny2168/Dockers/crondock/data/scripts/vw-sync.sh`.
  5. Created configuration directory `/Users/benny2168/Dockers/crondock/data/vault-sync/` with template `vault-sync.env` (and repo example `scripts/vault-sync/vault-sync.env.example`).
  6. Registered Job #9 in CronDock database with schedule `*/15 * * * *`.
- **Validation**:
  - `vw-sync:latest` container tested against missing config validation, logging clean error.
  - Runner script `vw-sync.sh` tested inside `crondock` container via `docker exec`.
  - CronDock restarted and confirmed healthy (`/api/health` -> 200).
