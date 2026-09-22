# Notes for Next Session — CronDock

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
- **Uploadable scripts as a first-class UI feature**: Add UI section under Settings or Jobs for uploading, editing, listing, and deleting shell scripts stored in `/data/scripts/`.
- **Per-job secrets/env vars**: Allow shell jobs to define custom environment variables passed to script execution.
- **Failover Verification Drill**: Document / simulate UDM manual port-forward flip from `192.168.1.140:443` (Mac Mini) to `192.168.1.121:8443` (Synology NPM standby).
- **Push commits**: Push local git commits to `mtcdtech/crondock` remote on `main`.

## Retained Backlog
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
