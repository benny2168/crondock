# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.2.0`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`)

## Active Status
- **Authentication**: Authentik SSO OIDC integrated (`auth.abraham16.com`).
- **HTTP Job Resilience**: Added 300s timeout default, configurable `HTTP_TIMEOUT` setting, automatic 3-attempt retry loop with exponential backoff on transient errors (timeouts, connection drops, 502/503/504, 409), and pretty-printed JSON response formatting.
- **Schedule Staggering**: Abraham Docker image prune scheduled at 3:30 AM (`30 3 * * *`) off the 3:00 AM DSM peak.
- **UI Enhancements**: Added elapsed runtime calculation (`⏱ duration_ms`), clean status badge mapping (`HTTP 200`, `Timeout / Error`), and updated logo subtitle to `v1.2.0`.
- **Container**: `benny2168/crondock:1.2.0` running on Ben-Mac-Mini.
- **Production Verification**: `/api/health` confirmed responding with `{"ok": true, "version": "1.2.0"}`.
