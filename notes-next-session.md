# Notes for Next Session — CronDock

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
