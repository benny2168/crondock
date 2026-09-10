# Change Tracker — CronDock

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
