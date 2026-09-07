# CronDock — Agent Instructions

## Project Overview
CronDock is a lightweight visual cron job manager with a web UI built with FastAPI, APScheduler, and SQLite.

## Environments & Deployments
- **Abraham Deployment**: Ben-Mac-Mini (Portainer Endpoint ID `3` via `https://docker.abraham16.com`).
  - **Host URL**: `https://cron.abraham16.com`
  - **Port**: `3900`
  - **Auth**: Authentik OIDC (`https://auth.abraham16.com`)
  - **Data Volume**: `/Users/benny2168/Dockers/crondock/data:/data`
- **Canonical Repository**: `mtcdtech/crondock` on GitHub (`main` branch).

## Operating Standards
- Follow the semantic versioning convention `major.minor.patch` in `app/main.py` (`version` in FastAPI and `/api/health`).
- Expose and update the version number with every meaningful release.
- Maintain persistent project memory files: `current-state.md`, `notes-next-session.md`, and `change-tracker.md`.
- Verify production deployments via CLI-accessible signals (e.g. `/api/health`, container inspect, and OIDC discovery endpoints).
