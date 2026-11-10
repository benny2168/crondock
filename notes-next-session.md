# Notes for Next Session — CronDock

## Recently Completed (2026-11-09)
**Project Finalization, Security Hardening & Test Suite Formalization (v1.4.2)**:
- Externalized all hardcoded credentials (`OIDC_CLIENT_SECRET`, `SESSION_SECRET`, `ABRAHAM_PORTAINER_TOKEN`, `MTCD_PORTAINER_TOKEN`, `IAM_API_KEY`, `VW_STANDBY_ADMIN_TOKEN`, `VW_STANDBY_SSO_CLIENT_ID`, `VW_STANDBY_SSO_CLIENT_SECRET`) from `docker-compose*.yml`, `app/database.py`, and `scripts/` into `.env` and CronDock's `settings` table; added `.env.example`, `.dockerignore`, and updated `.gitignore`.
- Added automatic environment variable injection of CronDock `settings` into `_run_shell` (`app/scheduler.py`) and `test_run_script` (`app/scripts_manager.py`), plus `follow_redirects=True` on HTTP jobs.
- Added secret masking (`••••••••••••`) on `GET /api/settings`, security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), `/robots.txt`, `/sitemap.xml` (404), and `404 JSONResponse` for unknown `/api/*` paths.
- Fixed UI static audit findings (`#script-search-input` and `#tl-filter-job` flex wrapping), replaced native browser `confirm()` in `closeScriptEditor()` with an inline confirmation pattern, added URL section sync (`?section=...`), and improved WCAG AA text contrast (`--muted: #94a3b8`).
- Added formal automated test suite (`tests/test_crondock.py`, 6/6 passing) and comprehensive `README.md`.

**MTCD Domain Migration & Vaultwarden Sync Self-Healing Fixes (v1.4.1)**:
- **MTCD Portainer Cleanups (Jobs #10 & #11)**:
  - Updated `MTCD_PORTAINER_URL` in CronDock `settings` (and seed defaults in `app/database.py` + `scripts/docker-cleanup.sh`) from `https://docker.server.mtcd.org` to `https://docker.mtcd.org`, resolving `HTTP 301 Moved Permanently` failures on `POST` requests.
- **Vaultwarden Sync (Job #9)**:
  - Updated `MTCD_URL` from `https://pw.server.mtcd.org` to `https://pw.mtcd.org` across `vault-sync.env` and `scripts/vault-sync/sync.py`.
  - Updated `authenticate_and_unlock` in `scripts/vault-sync/sync.py` to log out before running `bw config server` when switching server URLs.
  - Added self-healing `docker image inspect vw-sync:latest` check in `vw-sync.sh` to automatically build `vw-sync:latest` from `/data/vault-sync` if ever pruned/missing locally, and updated local host `crontab` cleanup script (`~/Antigravity/scripts/docker-cleanup.sh`) to `dangling=true` so ephemeral/standby images are preserved.
  - Verified all 11 jobs in CronDock (`#1, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12`) are enabled and green (`last_run_success = True`).

## Recently Completed (2026-10-03)
**In-Browser Script Manager with Syntax Correction (v1.4.0)**:
- **Full In-Browser Script Management**: Implemented dedicated `📜 Scripts` section with card view, metadata (size, timestamps, permissions 0755), search filter, and cross-referenced job linkages.
- **CodeMirror Code Editor**: Embedded local CodeMirror 5 with dark theme matching CronDock's palette, syntax modes for Bash and Python, matching brackets, active line highlighting, unsaved changes tracking, and keyboard shortcuts (`Ctrl/Cmd+S` save, `Ctrl/Cmd+Shift+F` auto-fix).
- **Deep Syntax Correction Engine**: Built `app/scripts_manager.py` with real-time `bash -n` validation and Python AST parsing.
- **1-Click Auto-Fix**: Automatically detects and corrects Windows CRLF line endings to Unix LF, replaces Unicode typography/smart quotes (`“”‘’—`) with ASCII equivalents, inserts shebang if missing, and trims trailing whitespace.
- **In-Browser Test Runner**: Executes scripts in container subshell with live output streaming, exit code capture, and millisecond timing before scheduling.
- **Multi-File Drag & Drop & Upload**: Supports dragging script files directly into the browser drop zone.
- **Job Drawer Integration**: Added script selector dropdown to automatically populate `/data/scripts/{name}` into shell commands with 1-click edit jump.

## Recently Completed (2026-09-21)
Vaultwarden Standby Restore & CronDock Log Output Streaming:
- **CronDock Log Streaming**:
  - Replaced `exec >> "$LOG" 2>&1` with `exec 1> >(tee -a "$LOG") 2>&1` in `vw-restore-standby.sh` and `npm-sync-standby.sh` so execution output streams simultaneously to disk and stdout/stderr for CronDock's database capture, permanently resolving `(no output)` across job executions.
- **Vaultwarden Standby Restore (Job #7)**:
  - Recreated `vaultwarden-standby` on standard bridge network on Synology.
  - Replaced fragile `t=2` Portainer restart with direct SSH host command (`docker restart -t 15`), and increased health check polling to 15 iterations (45s).
  - Verified run: Job 1010 completed with exit code 0 (`success=1`), health check returned HTTP 200, and full log stream saved.
- **NPM Standby Config Sync (Job #8)**:
  - Added `host.docker.internal` -> `192.168.1.120` rewrite in `npm-sync-standby.sh` so Mac Mini proxy host configs don't crash Nginx on Synology.
  - Replaced restart mechanism with direct SSH restart.
  - Verified run: Job 1011 completed with exit code 0 (`success=1`) and full log stream saved.
- **All 7 Jobs Green**: Every job in CronDock is enabled and showing `last_run_success = 1`.

## Immediate Backlog
- **Per-job secrets/env vars**: Allow shell jobs to define custom environment variables passed to script execution.
- **Failover Verification Drill**: Document / simulate UDM manual port-forward flip from `192.168.1.140:443` (Mac Mini) to `192.168.1.121:8443` (Synology NPM standby).
- **Push commits**: Push local git commits to `origin/abraham` and `mtcdtech/main`.


## Retained Backlog
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
