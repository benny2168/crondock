# Notes for Next Session — CronDock

## Immediate Verification (Post-Deploy v1.3.0)
1. Confirm `/api/health` returns `{"ok": true, "version": "1.3.0"}` at `https://cron.abraham16.com/api/health`.
2. Verify unauthorized requests to `/api/jobs` return HTTP 401.
3. Configure `API_KEY` setting value in CronDock Settings UI (`https://cron.abraham16.com`) with random 32+ char secret.
4. Verify programmatic request with `X-API-Key: <token>` returns 200 on `/api/jobs`.
5. Migrate Vaultwarden hourly backup job to CronDock via `/api/jobs` and remove legacy launchd job `com.abraham16.vw-backup` on Ben-Mac-Mini.
6. Monitor automated Docker cleanups at `30 3 * * *`, `35 3 * * *`, `40 3 * * *`, and `45 3 * * *`.

## Backlog / Planned Items
- Support optional webhooks / notifications (e.g. Discord, Telegram, NTFY) on job failure.
- If creating a fork or branch for Abraham-specific vs MTCD features, manage via branch `abraham-prod`.
