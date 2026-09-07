# Current State — CronDock

## Architecture & Overview
- **Service**: CronDock — Visual cron job manager with web UI
- **Active Repository**: `mtcdtech/crondock` (canonical repository, `main` branch)
- **Active Version**: `1.1.0`
- **Deployment Target**: Ben-Mac-Mini (Abraham Portainer endpoint 3)
- **Public URL**: `https://cron.abraham16.com`
- **Authentication**: Authentik SSO OIDC (`https://auth.abraham16.com`)

## Active Status
- **Authentication Cutover**: Completed migration from legacy Synology SSO to Authentik (`auth.abraham16.com`).
- **Authentik Application**: `crondock` (slug: `crondock`, provider ID: `6`).
- **UI Updates**: Login button label updated to "Sign in with Authentik SSO" with modern icon; logo subtitle bumped to `v1.1.0`.
- **Container**: Image `benny2168/crondock:1.1.0` running healthy on Ben-Mac-Mini.
- **Production Verification**: `/api/health` confirmed responding with `{"ok": true, "version": "1.1.0"}`.
