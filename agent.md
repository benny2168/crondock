# CronDock — Agent Instructions

## Project Overview
CronDock is a lightweight visual cron job and script manager with a web UI built with FastAPI, APScheduler, and SQLite (`WAL` mode).

## Environments & Deployments
- **Central CronDock Instance**: Ben-Mac-Mini (`https://cron.abraham16.com`, local port `3900`, Portainer Endpoint ID `3` via `https://docker.abraham16.com`).
  - Manages all scheduled jobs for both **Abraham** (`https://docker.abraham16.com`) and **MTCD** (`https://docker.mtcd.org`).
  - **Auth**: Authentik OIDC (`https://auth.abraham16.com`) + `X-API-Key` header for programmatic REST access.
  - **Data Volume**: `/Users/benny2168/Dockers/crondock/data:/data`
- **Repository**: `/Users/benny2168/Antigravity/crondock` (`abraham` branch).

## Critical Operational Rules
- **Never Open Bind-Mounted SQLite DB from Host macOS**: Never run macOS `sqlite3` directly against `/Users/benny2168/Dockers/crondock/data/crondock.db` while the `crondock` Linux container has it open in `WAL` mode over VirtioFS (causes cross-kernel mmap corruption and `sqlite3.OperationalError: disk I/O error`). Always query or mutate state via the REST API (`http://localhost:3900/api/...` with `X-API-Key`) or via `docker exec crondock ...`.
- **No Hardcoded Secrets**: Never commit API tokens, OIDC client secrets, or password hashes into git. Keep runtime secrets in `.env` (gitignored) or in the CronDock `settings` table (which automatically injects all settings as environment variables into child shell jobs and script test runs, and supports `{{SETTING_KEY}}` interpolation in HTTP jobs).
- **Versioning**: Follow semantic versioning (`major.minor.patch`) in `app/main.py` (`APP_VERSION`) and `app/static/index.html` (`.logo-sub`).
- **Verification**: Run `tests/test_crondock.py` and verify `/api/health` and job status after every deployment.
