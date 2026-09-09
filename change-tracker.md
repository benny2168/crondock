# Change Tracker — CronDock

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
