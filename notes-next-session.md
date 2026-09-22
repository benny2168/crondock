# Notes for Next Session — CronDock

## Recently Completed (2026-09-21)
SQLite Concurrency Hardening (WAL Mode) & Mac Mini Tasks Re-enabled (CronDock v1.3.3):
- **SQLite Concurrency Hardening**:
  - Configured Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `PRAGMA synchronous=NORMAL`, and `PRAGMA busy_timeout=30000` via SQLAlchemy event listeners and `create_engine(connect_args={"timeout": 30})`.
  - Completely resolved `database is locked` OperationalErrors during job update / toggle requests caused by concurrent `AuthMiddleware` / API token lookups and scheduler threads.
- **Mac Mini Docker Cleanups Re-enabled & Verified**:
  - Job #4 (`Docker Containers Cleanup — Mac Mini` at `40 3 * * *`): Re-enabled; manual test run completed in 68ms (HTTP 200).
  - Job #5 (`Docker Images Cleanup — Mac Mini` at `45 3 * * *`): Re-enabled; manual test run completed (HTTP 200).
- **CronDock Container Deployed**:
  - Built and deployed `benny2168/crondock:1.3.3`.
  - Health check on `https://cron.abraham16.com/api/health` confirmed live with version `1.3.3`.

## Immediate Backlog
- **Uploadable scripts as a first-class UI feature**: Add UI section under Settings or Jobs for uploading, editing, listing, and deleting shell scripts stored in `/data/scripts/`.
- **Per-job secrets/env vars**: Allow shell jobs to define custom environment variables passed to script execution.
- **Failover Verification Drill**: Document / simulate UDM manual port-forward flip from `192.168.1.140:443` (Mac Mini) to `192.168.1.121:8443` (Synology NPM standby).
- **Push commits**: Push local git commits to `mtcdtech/crondock` remote on `main`.

## Retained Backlog
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
