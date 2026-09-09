# Notes for Next Session — CronDock

## Recently Completed (2026-09-08)
v1.3.1 shipped and fully wired for host-ops shell jobs:
- Container recreated with `-v /var/run/docker.sock:/var/run/docker.sock`, `-v /Users/benny2168/.ssh/id_ed25519:/root/.ssh/id_ed25519:ro`, `-v /Users/benny2168/.ssh/known_hosts:/root/.ssh/known_hosts:ro`, `-v /Users/benny2168/Dockers/backups:/host-backups`. Attached to both `crondock_default` and `proxynet`. All env vars carried over via `--env-file`.
- Verified inside container: `docker`, `sqlite3`, `rsync`, `ssh`, `tar` all resolve. Docker socket works (`docker ps` sees all host containers). SSH to `ben@100.91.132.90` succeeds using mounted key + known_hosts.
- Job #6 "Vaultwarden Backup" created via `POST /api/jobs` with `type=shell`, schedule `7 * * * *`, command `bash /data/scripts/vw-backup-crondock.sh`. Ran end-to-end via `POST /api/jobs/{id}/run` in 2.5 seconds. Tarball landed on Synology (18.5MB).
- Legacy launchd `com.abraham16.vw-backup` unloaded and plist archived as `.disabled-20260908`. Confirmed via `launchctl list | grep -i vw` returns empty.
- Backup container `crondock_v130_backup` still present for 24h rollback path; can be `docker rm -f` after 2026-09-09.

## Immediate Backlog
- **Uploadable scripts as a first-class UI feature**: today scripts must be dropped into `/data/scripts/` via file manager / SSH. Add a UI section under Settings or Jobs for uploading, editing, listing, and deleting shell scripts stored in the data volume. Reference them from Shell jobs via a dropdown.
- **Per-job secrets/env vars**: Vaultwarden backup script has host paths and Synology hostname hardcoded. If we generalize, jobs should be able to define `env: {SYNOLOGY_HOST: "..."}` overrides passed to the shell invocation.
- **Rollback cleanup**: after 24-48h of stable v1.3.1, remove `crondock_v130_backup` container.

## Portfolio-Wide Follow-Ons (parked, not for CronDock directly but adjacent)
- Move Nginx Proxy Manager `/data` and `/letsencrypt` sync to Synology into a CronDock shell job (same pattern as vw-backup: SSH to Synology mounted, rsync hourly).
- Same for any other host-level data (Portainer stack backups, Authentik postgres dumps, etc.).
- Standby Vaultwarden container on Synology with hourly restore from latest backup tarball — pairs with UDM port-forward manual failover procedure (Ben's decision on 2026-09-08 to skip auto-failover and use UDM port-forward flip as the manual cutover mechanism).

## Backlog Retained from Prior Sessions
- Support optional webhooks / notifications (Discord, Telegram, NTFY) on job failure.
- If creating a fork or branch for Abraham-specific vs MTCD features, manage via branch `abraham-prod`.
