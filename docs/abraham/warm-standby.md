# Abraham warm-standby topology

## What this is

Two "warm standby" containers on Abraham Synology, kept fresh via hourly
CronDock jobs. On Ben-Mac-Mini failure, a manual UDM port-forward flip
promotes Synology to serve production traffic within ~60 minutes of the
last sync.

## Components

| Role | Primary (Ben-Mac-Mini) | Standby (Abraham Synology 192.168.1.121) |
|---|---|---|
| Vaultwarden | container `vaultwarden`, ports 5151/3012, SSO=on, `pw.abraham16.com` | container `vaultwarden-standby`, ports 5151/3012, SSO=off, master password only |
| NPM | container `nginx-proxy`, ports 80/443/81 | container `nginx-proxy-standby`, ports 8080/8443/8081 |
| CronDock | container `crondock`, port 3900, runs both sync jobs | — |

## Sync cadence

- **:07** — Job #6: `vaultwarden-backup.sh` writes `vw-*.tgz` to Synology
- **:17** — Job #7: `vw-restore-standby.sh` extracts latest tarball into
  standby's `/data`, restarts container, verifies `/alive`
- **:22** — Job #8: `npm-sync-standby.sh` rsyncs primary NPM `/data` and
  `/etc/letsencrypt` into standby's volumes

## Failover procedure (manual, ~5 min)

1. Confirm mini is down (ping, tailscale status, or UDM port monitor)
2. Log into UDM at https://<udm-ip>/network/settings/routing-firewall/port-forwarding
3. Change existing port-forward rules:
   - `WAN 443 → 192.168.1.140:443` becomes `WAN 443 → 192.168.1.121:8443`
   - `WAN 80 → 192.168.1.140:80` becomes `WAN 80 → 192.168.1.121:8080`
4. Save. Traffic flips within seconds.
5. Test: `curl -I https://pw.abraham16.com` should return 200 from standby.
6. Users log into Vaultwarden with their **master password** (SSO won't
   work because Authentik lives on the dead mini).

## Failback procedure

Reverse step 3 once the mini is healthy again. Standby continues to catch
sync updates in the meantime.

## Known limitations

- **SSO gap:** Vaultwarden standby is master-password-only. Users who forgot
  their master password can't recover without Authentik. Documented tech
  debt: build an Authentik standby on Synology in a future round.
- **~60min RPO:** Worst case, standby is up to 60 minutes stale.
- **Manual failover:** No auto-detection. Ben must decide + flip UDM rules.
  Chosen intentionally over auto-failover complexity for a home setup.
- **DSM holds 80/443:** Synology's system nginx + Apache + WebDAVServer
  packages own the privileged ports. Using 8080/8443/8081 for NPM standby
  with UDM handling the port translation on failover.

## Rollback of warm-standby entirely

Everything is additive; nothing on the mini primaries changes.

```bash
# 1. Delete Portainer stacks
TOK=<portainer-token>
curl -X DELETE -H "X-API-Key: $TOK" "https://docker.abraham16.com/api/stacks/7?endpointId=5&external=false"
curl -X DELETE -H "X-API-Key: $TOK" "https://docker.abraham16.com/api/stacks/8?endpointId=5&external=false"

# 2. Delete CronDock jobs 7 and 8 via API
CRON=<crondock-api-key>
curl -X DELETE -H "X-API-Key: $CRON" http://127.0.0.1:3900/api/jobs/7
curl -X DELETE -H "X-API-Key: $CRON" http://127.0.0.1:3900/api/jobs/8

# 3. Optional: remove Synology data directories
ssh ben@100.91.132.90 "rm -rf /volume1/docker/vaultwarden-standby /volume1/docker/nginx-proxy-standby"

# 4. Optional: recreate CronDock without the 2 NPM source mounts
#    (see docker-compose.abraham.yml — remove the last two volume lines)
```

## References

- Runbook: `/home/user/workspace/warm-standby-handoff-runbook.md` (Perplexity)
- Related repos: mtcdtech/crondock (upstream)
