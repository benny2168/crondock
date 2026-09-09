import base64
import hashlib
import json
import os
import secrets
from functools import partial
from typing import Optional

import asyncio
import requests as _requests
from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# ── Config ─────────────────────────────────────────────────────────────────

OIDC_CLIENT_ID      = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET  = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_DISCOVERY_URL  = os.getenv("OIDC_DISCOVERY_URL", "")
OIDC_REDIRECT_URI   = os.getenv("OIDC_REDIRECT_URI", "")

# AUTH_PROVIDER controls provider-specific behaviour:
#   "synology" — adds synossoJSSDK=False to the auth URL (Synology quirk)
#   "oidc"     — standard OIDC redirect flow, no extra params (Authentik, etc.)
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "oidc").lower()

SESSION_SECRET      = os.getenv("SESSION_SECRET", secrets.token_hex(32))
SESSION_COOKIE      = os.getenv("SESSION_COOKIE_NAME", "crondock_session")
SESSION_MAX_AGE     = int(os.getenv("SESSION_MAX_AGE_HOURS", "24")) * 3600

# API key for IAM portal integration (auto-generated if not set)
IAM_API_KEY = os.getenv("IAM_API_KEY", "")

_session_s = URLSafeTimedSerializer(SESSION_SECRET, salt="session")
_state_s   = URLSafeTimedSerializer(SESSION_SECRET, salt="oidc-state")

# ── OIDC discovery cache ────────────────────────────────────────────────────

_oidc_config: Optional[dict] = None


async def get_oidc_config() -> dict:
    global _oidc_config
    if _oidc_config:
        return _oidc_config
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        partial(_requests.get, OIDC_DISCOVERY_URL, timeout=15)
    )
    resp.raise_for_status()
    _oidc_config = resp.json()
    return _oidc_config


# ── State cookie (short-lived, for CSRF protection) ───────────────────────

def set_state_cookie(response, state: str):
    token = _state_s.dumps({"state": state})
    response.set_cookie(
        "crondock_oidc_state", token,
        max_age=600, httponly=True, samesite="lax", secure=True,
    )


def get_state_data(request: Request) -> Optional[dict]:
    token = request.cookies.get("crondock_oidc_state")
    if not token:
        return None
    try:
        return _state_s.loads(token, max_age=600)
    except (SignatureExpired, BadSignature):
        return None


# ── Session cookie ──────────────────────────────────────────────────────────

def create_session(response, user: dict):
    # Prefer full name → display_name → username fallback
    name = (
        user.get("name")
        or user.get("display_name")
        or user.get("preferred_username")
        or user.get("email", "")
    )
    data = {
        "sub":      user.get("sub", ""),
        "username": user.get("username") or user.get("preferred_username", ""),
        "email":    user.get("email", ""),
        "name":     name,
    }
    token = _session_s.dumps(data)
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True, samesite="lax", secure=True,
    )


def clear_session(response):
    response.delete_cookie(SESSION_COOKIE, samesite="lax", secure=True)


def get_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return _session_s.loads(token, max_age=SESSION_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


# ── JWT payload decode (no sig verify — token received directly over HTTPS) ─

def decode_jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (4 - len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


# ── Token exchange ──────────────────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens using requests in a thread executor.
    Uses the synchronous `requests` library (same as slideshow app) to avoid
    httpx timeout issues with Synology SSO over OrbStack networking."""
    cfg = await get_oidc_config()
    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  OIDC_REDIRECT_URI,
        "client_id":     OIDC_CLIENT_ID,
        "client_secret": OIDC_CLIENT_SECRET,
    }
    _log.info(f"Token exchange → {cfg['token_endpoint']}")

    def _do_post():
        return _requests.post(
            cfg["token_endpoint"],
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
            verify=True,
        )

    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, _do_post)

    _log.info(f"Token response: HTTP {resp.status_code} — {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"SSO error: {data.get('error')} — {data.get('error_description', '')}")
    return data


# ── API Key Verification ───────────────────────────────────────────────────

def verify_api_key(token: str) -> bool:
    """Verify an X-API-Key token against the API_KEY setting in the database.
    Returns False if token is empty, API_KEY setting is empty/missing, or mismatch.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not token or not token.strip():
        return False
    try:
        from database import SessionLocal, Setting
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == "API_KEY").first()
            if not setting or not setting.value:
                return False
            expected = setting.value.strip()
            if not expected:
                return False
            return secrets.compare_digest(token.strip(), expected)
        finally:
            db.close()
    except Exception as e:
        _log.warning(f"Failed to verify API key: {e}")
        return False

