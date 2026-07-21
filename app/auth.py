import base64
import hashlib
import json
import os
import secrets
from typing import Optional

import httpx
from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# ── Config ─────────────────────────────────────────────────────────────────

OIDC_CLIENT_ID      = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET  = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_DISCOVERY_URL  = os.getenv("OIDC_DISCOVERY_URL", "")
OIDC_REDIRECT_URI   = os.getenv("OIDC_REDIRECT_URI", "https://cron.abraham16.com/auth/callback")

SESSION_SECRET      = os.getenv("SESSION_SECRET", secrets.token_hex(32))
SESSION_COOKIE      = os.getenv("SESSION_COOKIE_NAME", "crondock_session")
SESSION_MAX_AGE     = int(os.getenv("SESSION_MAX_AGE_HOURS", "24")) * 3600

_session_s = URLSafeTimedSerializer(SESSION_SECRET, salt="session")
_state_s   = URLSafeTimedSerializer(SESSION_SECRET, salt="oidc-state")

# ── OIDC discovery cache ────────────────────────────────────────────────────

_oidc_config: Optional[dict] = None


async def get_oidc_config() -> dict:
    global _oidc_config
    if _oidc_config:
        return _oidc_config
    async with httpx.AsyncClient(verify=True, timeout=10) as client:
        resp = await client.get(OIDC_DISCOVERY_URL)
        resp.raise_for_status()
        _oidc_config = resp.json()
    return _oidc_config


# ── PKCE helpers ────────────────────────────────────────────────────────────

def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


# ── State cookie (short-lived, for PKCE round-trip) ────────────────────────

def set_state_cookie(response, state: str, verifier: str):
    token = _state_s.dumps({"state": state, "verifier": verifier})
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
    data = {
        "sub":      user.get("sub", ""),
        "username": user.get("username") or user.get("preferred_username", ""),
        "email":    user.get("email", ""),
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

async def exchange_code(code: str, code_verifier: str) -> dict:
    cfg = await get_oidc_config()
    async with httpx.AsyncClient(verify=True, timeout=15) as client:
        resp = await client.post(
            cfg["token_endpoint"],
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  OIDC_REDIRECT_URI,
                "client_id":     OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()
