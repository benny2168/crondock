# Notes for Next Session — CronDock

## Next: complete Abraham warm-standby handoff (Phase 2+)

The `abraham` branch is now created with all scaffolding. Remaining work
to make warm-standby actually functional:

### 1. Deploy NPM standby container on Abraham Synology
- Portainer stack #8 was created and force-deleted earlier because
  `jc21/nginx-proxy-manager:latest` image pull kept timing out via the
  openresty proxy. Image is NOT yet on Synology.
- Fix: pre-pull image via DSM Container Manager UI at
  http://192.168.1.121:5000 → Registry tab → search
  `jc21/nginx-proxy-manager` → Download tag `latest`. Then redeploy
  the stack via Portainer with the compose YAML from
  `docs/abraham/warm-standby.md`.

### 2. Recreate CronDock container with 2 new bind mounts
- Current running container `crondock` has 5 mounts. Need to add:
  - `-v /Users/benny2168/Dockers/nginx-proxy-data:/nginx-proxy-src/data:ro`
  - `-v /Users/benny2168/Dockers/nginx-proxy-letsencrypt:/nginx-proxy-src/letsencrypt:ro`
- Preferred path: create `.env.abraham` from the example, then
  `docker compose --env-file .env.abraham -f docker-compose.abraham.yml up -d`
  (docker compose will recreate the container with the new mount list).
- Preserve `crondock_v130_backup` rollback container.

### 3. Create CronDock jobs #7 and #8 via API
```bash
# Job #7: Vaultwarden Standby Restore
curl -sS -X POST -H "X-API-Key: $CRONDOCK_TOKEN" -H "Content-Type: application/json" \
  http://127.0.0.1:3900/api/jobs \
  -d '{"name":"Vaultwarden Standby Restore","schedule":"17 * * * *","type":"shell","command":"bash /data/scripts/vw-restore-standby.sh","enabled":true}'

# Job #8: NPM Config Sync
curl -sS -X POST -H "X-API-Key: $CRONDOCK_TOKEN" -H "Content-Type: application/json" \
  http://127.0.0.1:3900/api/jobs \
  -d '{"name":"NPM Config Sync to Synology","schedule":"22 * * * *","type":"shell","command":"bash /data/scripts/npm-sync-standby.sh","enabled":true}'
```

Note: scripts on host live at `/Users/benny2168/Dockers/crondock/data/scripts/`,
mounted into container at `/data/scripts/`. Copy them from the repo's
`scripts/abraham/` into the CronDock data dir before creating jobs.

### 4. Trigger initial syncs and verify
```bash
curl -X POST -H "X-API-Key: $CRONDOCK_TOKEN" http://127.0.0.1:3900/api/jobs/7/run
curl -X POST -H "X-API-Key: $CRONDOCK_TOKEN" http://127.0.0.1:3900/api/jobs/8/run
```

### 5. Update Brain wiki
Add page at `memory/knowledge/concepts/vaultwarden-npm-warm-standby.md`
with the topology from `docs/abraham/warm-standby.md`.

## Tech debt: secrets in main branch compose

`docker-compose.yml` on `mtcdtech/main` has hardcoded `OIDC_CLIENT_SECRET`
and `SESSION_SECRET`. Not fixed in this fork's scope, but worth noting:
those tokens should be rotated at some point and mtcdtech/main should
adopt env-var pattern like `docker-compose.mtcd.yml` and
`docker-compose.abraham.yml` already do.

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
