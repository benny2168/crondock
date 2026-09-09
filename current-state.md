# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.3.0`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`) + Programmatic API Token (`X-API-Key` header)

## Active Status
- **Authentication**: Authentik SSO OIDC integrated (`auth.abraham16.com`) for web UI users, plus programmatic API token authentication via `X-API-Key` header for `/api/*` endpoints backed by constant-time secret comparison against the database `API_KEY` setting.
- **HTTP Job Resilience**: 300s timeout default, configurable `HTTP_TIMEOUT` setting, automatic 3-attempt retry loop with exponential backoff on transient errors (timeouts, connection drops, 502/503/504, 409), and pretty-printed JSON response formatting.
- **Multi-Host Docker Cleanups Configured**:
  1. `Docker Containers Cleanup — Abraham Synology` (`30 3 * * *`): Prunes stopped/unused containers on Abraham Synology NAS (Endpoint 5).
  2. `Docker Images Cleanup — Abraham Synology` (`35 3 * * *`): Prunes dangling/unused images on Abraham Synology NAS (Endpoint 5).
  3. `Docker Containers Cleanup — Mac Mini` (`40 3 * * *`): Prunes stopped/unused containers on Ben-Mac-Mini (Endpoint 3).
  4. `Docker Images Cleanup — Mac Mini` (`45 3 * * *`): Prunes dangling/unused images on Ben-Mac-Mini (Endpoint 3).
- **UI Enhancements**: Added elapsed runtime calculation (`⏱ duration_ms`), clean status badge mapping (`HTTP 200`, `Timeout / Error`), and updated logo subtitle to `v1.3.0`.
- **Container**: `benny2168/crondock:1.3.0` built on Ben-Mac-Mini.
- **Production Verification**: Deploy-first validation pending production rollout to Portainer stack at `cron.abraham16.com`. API token programmatic access and `/api/health` v1.3.0 verification scheduled post-deploy.
