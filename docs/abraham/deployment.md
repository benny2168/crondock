# CronDock deployment on Ben-Mac-Mini (Abraham)

## Prerequisites

- Docker + `docker compose` on Mac-mini
- `/Users/benny2168/Dockers/crondock/data/` exists and writable
- `~/.ssh/id_ed25519` (no passphrase) with pubkey installed on Abraham
  Synology at `ben@100.91.132.90`
- Authentik application `crondock` provisioned at
  `https://auth.abraham16.com/application/o/crondock/`
- Nginx Proxy Manager proxy_host for `cron.abraham16.com` → mini port 3900
- `.env.abraham` present in repo root (copy from `.env.abraham.example`)

## Deploy

```bash
cd /Users/benny2168/Antigravity/crondock
git checkout abraham
git pull origin abraham
docker compose --env-file .env.abraham -f docker-compose.abraham.yml pull
docker compose --env-file .env.abraham -f docker-compose.abraham.yml up -d
docker logs -f crondock  # sanity check
```

## Verify

- UI: https://cron.abraham16.com (Authentik SSO)
- API: `curl -H "X-API-Key: <key>" http://127.0.0.1:3900/api/jobs`

## Rollback

```bash
docker compose -f docker-compose.abraham.yml down
# Previous version container `crondock_v130_backup` remains as 24h rollback:
docker start crondock_v130_backup
docker rename crondock_v130_backup crondock
```
