# Notes for Next Session — CronDock

## Immediate Verification & Follow-on Work (Post-Deploy v1.3.1)
Parent orchestrator will execute the following steps once v1.3.1 is shipped:
1. **Container Recreation with Host Mounts**: Recreate CronDock container on Ben-Mac-Mini adding `-v /var/run/docker.sock:/var/run/docker.sock` and `-v /Users/benny2168/.ssh/id_ed25519:/root/.ssh/id_ed25519:ro`.
2. **Verify Tooling in Production**:
   - Confirm `/api/health` returns `{"ok": true, "version": "1.3.1"}`.
   - Run `docker exec crondock which docker sqlite3 rsync ssh tar` to confirm all CLIs resolve.
3. **Drop Backup Script**: Drop `vw-backup-v2.sh` into `/Users/benny2168/Dockers/crondock/data/scripts/` (accessible as `/data/scripts/vw-backup-v2.sh` inside container).
4. **Configure Host Verification**: Populate `known_hosts` via `docker exec crondock sh -c "ssh-keyscan 100.91.132.90 >> /root/.ssh/known_hosts"`.
5. **Create CronDock Job**: Create Vaultwarden hourly backup job via API (`POST /api/jobs`) with schedule `7 * * * *` and command `bash /data/scripts/vw-backup-v2.sh`.
6. **Trigger and Verify**: Trigger job via `POST /api/jobs/{id}/run` and confirm successful execution and Synology tarball sync.
7. **Retire Launchd Job**: Disable and delete legacy launchd job `com.abraham16.vw-backup`.

## Backlog / Planned Items
- Support optional webhooks / notifications (e.g. Discord, Telegram, NTFY) on job failure.
- If creating a fork or branch for Abraham-specific vs MTCD features, manage via branch `abraham-prod`.
