# CronDock

CronDock is a self-hosted visual cron job and script manager built with **FastAPI**, **APScheduler**, and **SQLite** (WAL mode). It provides a modern dark-mode web dashboard for scheduling shell commands and HTTP requests, editing and syntax-validating scripts in-browser with CodeMirror, viewing execution timelines and logs, and authenticating via OpenID Connect (OIDC) or API tokens.

---

## Key Features

- **Dual Job Engine (`shell` & `http`)**:
  - **Shell Jobs**: Execute Bash/Python scripts or inline shell commands with automatic environment variable injection from the CronDock Settings store.
  - **HTTP Jobs**: Trigger remote webhooks or REST endpoints (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`) with custom headers, request bodies, redirect handling, and `{{SETTING_KEY}}` template interpolation.
- **Integrated Script Studio (`/data/scripts`)**:
  - Built-in CodeMirror editor with Bash and Python syntax highlighting.
  - Real-time syntax validation (`bash -n`, `py_compile`) and one-click auto-formatting (CRLF normalization, smart-quote replacement, shebang insertion, and `0755` permissions).
  - Drag-and-drop multi-file upload and instant in-container test execution console.
- **Execution Timeline & Log Retention**:
  - Interactive list and monthly calendar views showing past runs (success/fail/running) and upcoming scheduled fire times.
  - Automatic pruning to the most recent 200 log entries per job.
- **Enterprise Authentication & Security**:
  - Supports **Authentik / Standard OIDC** (`AUTH_PROVIDER=oidc`) and **Synology SSO** (`AUTH_PROVIDER=synology`).
  - Programmatic REST API access via `X-API-Key` header with constant-time comparison (`secrets.compare_digest`).
  - Secret settings (`is_secret=True`) are masked (`••••••••••••`) across all API responses and UI views while remaining available to scheduled jobs at runtime.

---

## Project Architecture

```text
crondock/
├── app/
│   ├── main.py              # FastAPI application, AuthMiddleware, REST API & SPA routes
│   ├── auth.py              # OIDC / Synology SSO authentication & session cookie signing
│   ├── database.py          # SQLAlchemy SQLite (WAL) models: Job, JobLog, Setting
│   ├── models.py            # Pydantic request/response schemas
│   ├── scheduler.py         # APScheduler BackgroundScheduler, shell & HTTP runners
│   ├── scripts_manager.py   # /data/scripts file manager, syntax checker & test runner
│   ├── requirements.txt     # Pinned Python dependencies
│   └── static/              # Vanilla JS SPA (index.html, login.html, app.js, style.css)
├── scripts/                 # Operational & maintenance scripts synced to /data/scripts
├── tests/
│   └── test_crondock.py     # Automated unittest + FastAPI TestClient verification suite
├── Dockerfile               # Python 3.12-slim image with Docker CLI, rsync, OpenSSH, curl
├── docker-compose.yml       # Primary deployment compose file
└── .env.example             # Documented environment variable template
```

---

## Quick Start (Docker Compose)

1. **Copy the environment template and configure your credentials**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and populate `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, and `SESSION_SECRET`.

2. **Build and start the container**:
   ```bash
   docker compose up -d --build
   ```

3. **Verify health**:
   ```bash
   curl -s http://localhost:3900/api/health
   # {"status":"ok","version":"1.4.2","auth_provider":"oidc"}
   ```

---

## Environment Variables

All runtime secrets and host-specific paths are configured via environment variables (see [`.env.example`](file:///Users/benny2168/Antigravity/crondock/.env.example)):

| Variable | Description | Default |
| :--- | :--- | :--- |
| `CRONDOCK_PORT` | Host port mapped to container port `8000` | `3900` |
| `TZ` | Container and scheduler timezone | `America/Chicago` |
| `DATA_DIR` | Inside-container path for SQLite DB (`crondock.db`) | `/data` |
| `SCRIPTS_DIR` | Inside-container path for managed scripts | `/data/scripts` |
| `AUTH_PROVIDER` | Authentication backend (`oidc` or `synology`) | `oidc` |
| `LOGIN_PROVIDER_NAME` | Display label on the sign-in button | `Authentik SSO` |
| `OIDC_ISSUER` | OIDC provider discovery issuer URL (e.g. `https://auth.example.com/application/o/crondock/`) | — |
| `OIDC_CLIENT_ID` | OIDC client ID | — |
| `OIDC_CLIENT_SECRET` | OIDC client secret | — |
| `OIDC_REDIRECT_URI` | OIDC callback URL (e.g. `https://cron.example.com/auth/callback`) | — |
| `SESSION_SECRET` | Random 64-hex-character secret for signing session cookies | Auto-generated if unset |
| `IAM_API_KEY` | Bearer key for `/api/iam/roles` discovery | — |
| `API_KEY` | Optional default API key seeded into `settings` table | Auto-generated if unset |

---

## Running Tests & Quality Audits

Run the automated test suite inside the container or a local Python 3.12 virtual environment:

```bash
# Run unit & API integration tests
python3 -m unittest discover -s tests -v
```

Run the static security, UI, and privacy audits:

```bash
node ~/.gemini/config/scripts/audit-security.mjs
node ~/.gemini/config/scripts/audit-ui-static.mjs
node ~/.gemini/config/scripts/audit-pii.mjs
```

