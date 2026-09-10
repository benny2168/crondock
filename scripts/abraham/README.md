# Abraham CronDock scripts

Scripts invoked by CronDock jobs on Ben-Mac-Mini. All secrets come from
container env (populated by `.env.abraham` outside the repo).

## Scripts

- `vw-restore-standby.sh` — CronDock job #7. Restores the latest Vaultwarden
  backup tarball from Abraham Synology (populated by job #6) into the
  `vaultwarden-standby` container's data volume. Atomic swap: extract to
  `.new`, stop container, mv dirs, start container, delete `.old`.

- `npm-sync-standby.sh` — CronDock job #8. Rsyncs the primary NPM
  `/data` and `/etc/letsencrypt` directories from Ben-Mac-Mini into the
  standby container's volumes on Abraham Synology. Read-only source mounts
  are `/nginx-proxy-src/data` and `/nginx-proxy-src/letsencrypt` (see
  `docker-compose.abraham.yml`).

## Required env vars

Set via `.env.abraham` and loaded into the container's environment:

- `PORTAINER_URL`, `PORTAINER_TOKEN`, `PORTAINER_ENDPOINT_ID`
- `STANDBY_HOST` (Tailscale IP of Abraham Synology)
- `STANDBY_SSH_USER` (SSH user for Synology)

The scripts also expect the CronDock container to have:

- `/root/.ssh/id_ed25519` (mounted from mini's `~/.ssh/id_ed25519`)
- `/root/.ssh/known_hosts` (mounted from mini's `~/.ssh/known_hosts`)
- `/host-backups` (mounted from mini's `~/Dockers/backups`, for logs)
- `/nginx-proxy-src/data` and `/nginx-proxy-src/letsencrypt` (npm source, ro)
