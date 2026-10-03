#!/usr/bin/env python3
"""
Vaultwarden Multi-Instance Sync Bridge (MTCD <-> Abraham)
Preserves TOTP (2FA seeds) and Passkeys (FIDO2 credentials).

Runs non-interactively using the Bitwarden CLI (bw) with separate
data directories for session and server isolation.
"""

import os
import sys
import json
import uuid
import base64
import logging
import subprocess
from datetime import datetime, timezone
from dateutil.parser import isoparse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("vault-sync")

# Environment configuration
MTCD_URL = os.getenv("MTCD_URL", "https://pw.server.mtcd.org").rstrip("/")
MTCD_EMAIL = os.getenv("MTCD_EMAIL", "tech@mtcd.org")
MTCD_CLIENT_ID = os.getenv("MTCD_CLIENT_ID", "")
MTCD_CLIENT_SECRET = os.getenv("MTCD_CLIENT_SECRET", "")
MTCD_PASSWORD = os.getenv("MTCD_PASSWORD", "")
MTCD_SYNC_FOLDER = os.getenv("MTCD_SYNC_FOLDER", "Sync to Abraham")

ABRAHAM_URL = os.getenv("ABRAHAM_URL", "https://pw.abraham16.com").rstrip("/")
ABRAHAM_EMAIL = os.getenv("ABRAHAM_EMAIL", "ben@abraham16.com")
ABRAHAM_CLIENT_ID = os.getenv("ABRAHAM_CLIENT_ID", "")
ABRAHAM_CLIENT_SECRET = os.getenv("ABRAHAM_CLIENT_SECRET", "")
ABRAHAM_PASSWORD = os.getenv("ABRAHAM_PASSWORD", "")
ABRAHAM_SYNC_FOLDER = os.getenv("ABRAHAM_SYNC_FOLDER", "Sync to Abraham")

SYNC_MODE = os.getenv("SYNC_MODE", "bidirectional").lower()  # bidirectional, mtcd_to_abraham, abraham_to_mtcd
DATA_ROOT = os.getenv("BW_DATA_ROOT", "/bw-data")


def validate_config():
    missing = []
    if not MTCD_CLIENT_ID or not MTCD_CLIENT_SECRET or not MTCD_PASSWORD:
        missing.append("MTCD credentials (MTCD_CLIENT_ID, MTCD_CLIENT_SECRET, MTCD_PASSWORD)")
    if not ABRAHAM_CLIENT_ID or not ABRAHAM_CLIENT_SECRET or not ABRAHAM_PASSWORD:
        missing.append("Abraham credentials (ABRAHAM_CLIENT_ID, ABRAHAM_CLIENT_SECRET, ABRAHAM_PASSWORD)")
    if missing:
        logger.error(f"Missing required configuration: {', '.join(missing)}")
        logger.error("Please set them in your environment file before running.")
        sys.exit(1)


def run_bw_raw(app_dir, args, session=None, stdin_data=None, extra_env=None):
    """Execute Bitwarden CLI and return raw output."""
    env = os.environ.copy()
    env["BITWARDENCLI_APPDATA_DIR"] = app_dir
    if extra_env:
        env.update(extra_env)

    cmd = ["bw"] + args
    if session:
        cmd += ["--session", session]

    res = subprocess.run(
        cmd,
        env=env,
        input=stdin_data,
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(f"Command 'bw {' '.join(args)}' failed (code {res.returncode}): {err}")
    return res.stdout.strip()


def run_bw_json(app_dir, args, session=None, stdin_data=None, extra_env=None):
    """Execute Bitwarden CLI and parse JSON output."""
    out = run_bw_raw(app_dir, args, session=session, stdin_data=stdin_data, extra_env=extra_env)
    return json.loads(out) if out else None


def get_status(app_dir):
    try:
        return run_bw_json(app_dir, ["status"])
    except Exception:
        return {"status": "unauthenticated"}


def authenticate_and_unlock(name, app_dir, server_url, email, client_id, client_secret, password):
    """Log in with API key and unlock vault, returning the session token."""
    os.makedirs(app_dir, exist_ok=True)
    logger.info(f"Connecting to {name} ({server_url}) as {email}...")

    # Set server URL
    status = get_status(app_dir)
    if status.get("serverUrl") != server_url:
        logger.info(f"Setting server URL for {name} to {server_url}")
        run_bw_raw(app_dir, ["config", "server", server_url])
        status = get_status(app_dir)

    # Check authentication
    if status.get("status") == "unauthenticated" or status.get("userEmail") != email:
        if status.get("status") != "unauthenticated":
            logger.info(f"Logging out of previous account on {name}...")
            try:
                run_bw_raw(app_dir, ["logout"])
            except Exception:
                pass
        logger.info(f"Authenticating with API key for {name}...")
        api_env = {
            "BW_CLIENTID": client_id,
            "BW_CLIENTSECRET": client_secret
        }
        run_bw_raw(app_dir, ["login", "--apikey"], extra_env=api_env)

    # Unlock vault
    logger.info(f"Unlocking vault for {name}...")
    pwd_env = {"BW_PASSWORD": password}
    session = run_bw_raw(app_dir, ["unlock", "--passwordenv", "BW_PASSWORD", "--raw"], extra_env=pwd_env)

    # Synchronize vault
    logger.info(f"Syncing vault cache for {name}...")
    run_bw_raw(app_dir, ["sync"], session=session)

    return session


def get_or_create_folder(name, app_dir, session, folder_name, auto_create=True):
    """Get folder by name, optionally creating it if missing."""
    folders = run_bw_json(app_dir, ["list", "folders"], session=session) or []
    for f in folders:
        if f.get("name", "").strip().lower() == folder_name.strip().lower():
            return f["id"]

    if not auto_create:
        raise ValueError(f"Folder '{folder_name}' not found on {name}")

    logger.info(f"Folder '{folder_name}' not found on {name}. Creating it now...")
    encoded = base64.b64encode(json.dumps({"name": folder_name}).encode()).decode()
    created = run_bw_json(app_dir, ["create", "folder"], session=session, stdin_data=encoded)
    return created["id"]


def get_sync_uuid(item):
    """Retrieve _sync_uuid from item custom fields if present."""
    for field in item.get("fields") or []:
        if field.get("name") == "_sync_uuid" and field.get("value"):
            return field["value"].strip()
    return None


def set_sync_uuid(app_dir, session, item, sync_uuid):
    """Add _sync_uuid custom field to an item and persist it to the server."""
    item_id = item["id"]
    fields = [f for f in (item.get("fields") or []) if f.get("name") != "_sync_uuid"]
    fields.append({"name": "_sync_uuid", "value": sync_uuid, "type": 0})
    item["fields"] = fields

    encoded = base64.b64encode(json.dumps(item).encode()).decode()
    updated = run_bw_json(app_dir, ["edit", "item", item_id], session=session, stdin_data=encoded)
    return updated


def build_sync_payload(source_item, target_folder_id, sync_uuid):
    """Build item payload for target vault, preserving OTP and Passkeys."""
    login_obj = source_item.get("login") or {}

    sanitized_login = {
        "username": login_obj.get("username"),
        "password": login_obj.get("password"),
        "totp": login_obj.get("totp"),
        "uris": login_obj.get("uris", []),
        "fido2Credentials": login_obj.get("fido2Credentials", []),  # Passkeys
        "autofillOnPageLoad": login_obj.get("autofillOnPageLoad")
    }
    sanitized_login = {k: v for k, v in sanitized_login.items() if v is not None}

    # Filter out sync tracking fields from original fields
    custom_fields = [
        f for f in (source_item.get("fields") or [])
        if f.get("name") not in ("_sync_uuid", "_sync_last_synced_at")
    ]
    # Append fresh sync metadata
    custom_fields.append({"name": "_sync_uuid", "value": sync_uuid, "type": 0})
    custom_fields.append({
        "name": "_sync_last_synced_at",
        "value": datetime.now(timezone.utc).isoformat(),
        "type": 0
    })

    payload = {
        "type": source_item.get("type", 1),  # 1 = Login
        "name": source_item.get("name", "Untitled"),
        "notes": source_item.get("notes"),
        "favorite": source_item.get("favorite", False),
        "folderId": target_folder_id,
        "login": sanitized_login,
        "fields": custom_fields
    }
    return payload


def main():
    validate_config()

    mtcd_app_dir = os.path.join(DATA_ROOT, "mtcd")
    abraham_app_dir = os.path.join(DATA_ROOT, "abraham")

    logger.info("=== Starting Vaultwarden Multi-Instance Sync ===")
    logger.info(f"Sync Mode: {SYNC_MODE.upper()}")
    logger.info(f"Source Folder (MTCD): '{MTCD_SYNC_FOLDER}'")
    logger.info(f"Target Folder (Abraham): '{ABRAHAM_SYNC_FOLDER}'")

    session_mtcd = None
    session_abraham = None

    try:
        session_mtcd = authenticate_and_unlock(
            "MTCD", mtcd_app_dir, MTCD_URL, MTCD_EMAIL,
            MTCD_CLIENT_ID, MTCD_CLIENT_SECRET, MTCD_PASSWORD
        )
        session_abraham = authenticate_and_unlock(
            "Abraham", abraham_app_dir, ABRAHAM_URL, ABRAHAM_EMAIL,
            ABRAHAM_CLIENT_ID, ABRAHAM_CLIENT_SECRET, ABRAHAM_PASSWORD
        )

        # 1. Discover folders
        mtcd_folder_id = get_or_create_folder("MTCD", mtcd_app_dir, session_mtcd, MTCD_SYNC_FOLDER, auto_create=False)
        abraham_folder_id = get_or_create_folder("Abraham", abraham_app_dir, session_abraham, ABRAHAM_SYNC_FOLDER, auto_create=True)

        logger.info(f"MTCD Folder ID: {mtcd_folder_id}")
        logger.info(f"Abraham Folder ID: {abraham_folder_id}")

        # 2. Fetch items from both folders
        mtcd_items = run_bw_json(mtcd_app_dir, ["list", "items", "--folderid", mtcd_folder_id], session=session_mtcd) or []
        abraham_items = run_bw_json(abraham_app_dir, ["list", "items", "--folderid", abraham_folder_id], session=session_abraham) or []

        logger.info(f"Found {len(mtcd_items)} item(s) in MTCD '{MTCD_SYNC_FOLDER}'")
        logger.info(f"Found {len(abraham_items)} item(s) in Abraham '{ABRAHAM_SYNC_FOLDER}'")

        # Build index maps by _sync_uuid and by (name, username) fallback
        abraham_uuid_map = {}
        abraham_name_map = {}
        for item in abraham_items:
            u = get_sync_uuid(item)
            if u:
                abraham_uuid_map[u] = item
            uname = (item.get("login") or {}).get("username") or ""
            key = (item.get("name", "").strip().lower(), uname.strip().lower())
            abraham_name_map[key] = item

        mtcd_uuid_map = {}
        for item in mtcd_items:
            u = get_sync_uuid(item)
            if u:
                mtcd_uuid_map[u] = item

        created_count = 0
        updated_count = 0
        unchanged_count = 0

        # 3. Process items from MTCD -> Abraham
        for mtcd_item in mtcd_items:
            item_name = mtcd_item.get("name", "Unknown")
            sync_uuid = get_sync_uuid(mtcd_item)

            if not sync_uuid:
                # Check fallback match before creating a new UUID
                uname = (mtcd_item.get("login") or {}).get("username") or ""
                fallback_key = (mtcd_item.get("name", "").strip().lower(), uname.strip().lower())
                if fallback_key in abraham_name_map:
                    matched = abraham_name_map[fallback_key]
                    sync_uuid = get_sync_uuid(matched) or str(uuid.uuid4())
                else:
                    sync_uuid = str(uuid.uuid4())

                logger.info(f"Assigning new _sync_uuid [{sync_uuid}] to MTCD item '{item_name}'")
                mtcd_item = set_sync_uuid(mtcd_app_dir, session_mtcd, mtcd_item, sync_uuid)
                mtcd_uuid_map[sync_uuid] = mtcd_item

            # Check if this item exists in Abraham
            abraham_match = abraham_uuid_map.get(sync_uuid)
            if not abraham_match:
                uname = (mtcd_item.get("login") or {}).get("username") or ""
                fallback_key = (mtcd_item.get("name", "").strip().lower(), uname.strip().lower())
                abraham_match = abraham_name_map.get(fallback_key)

            if not abraham_match:
                # Create in Abraham
                logger.info(f"[CREATE -> Abraham] Syncing '{item_name}' (Passkeys: {len((mtcd_item.get('login') or {}).get('fido2Credentials', []))}, OTP: {'Yes' if (mtcd_item.get('login') or {}).get('totp') else 'No'})")
                payload = build_sync_payload(mtcd_item, abraham_folder_id, sync_uuid)
                encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                created = run_bw_json(abraham_app_dir, ["create", "item"], session=session_abraham, stdin_data=encoded)
                abraham_uuid_map[sync_uuid] = created
                created_count += 1
            else:
                # Item exists on both sides: compare revision dates
                mtcd_rev = isoparse(mtcd_item["revisionDate"])
                abraham_rev = isoparse(abraham_match["revisionDate"])

                if mtcd_rev > abraham_rev:
                    logger.info(f"[UPDATE -> Abraham] MTCD version is newer for '{item_name}' ({mtcd_rev} > {abraham_rev})")
                    payload = build_sync_payload(mtcd_item, abraham_folder_id, sync_uuid)
                    payload["id"] = abraham_match["id"]
                    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                    run_bw_json(abraham_app_dir, ["edit", "item", abraham_match["id"]], session=session_abraham, stdin_data=encoded)
                    updated_count += 1
                elif abraham_rev > mtcd_rev and SYNC_MODE == "bidirectional":
                    logger.info(f"[UPDATE -> MTCD] Abraham version is newer for '{item_name}' ({abraham_rev} > {mtcd_rev})")
                    payload = build_sync_payload(abraham_match, mtcd_folder_id, sync_uuid)
                    payload["id"] = mtcd_item["id"]
                    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                    run_bw_json(mtcd_app_dir, ["edit", "item", mtcd_item["id"]], session=session_mtcd, stdin_data=encoded)
                    updated_count += 1
                else:
                    unchanged_count += 1

        # 4. Check for Abraham-only items if bidirectional
        if SYNC_MODE == "bidirectional":
            for abraham_item in abraham_items:
                sync_uuid = get_sync_uuid(abraham_item)
                item_name = abraham_item.get("name", "Unknown")
                if sync_uuid and sync_uuid not in mtcd_uuid_map:
                    # Item exists in Abraham's sync folder but not yet in MTCD
                    logger.info(f"[CREATE -> MTCD] Syncing Abraham item '{item_name}' to MTCD...")
                    payload = build_sync_payload(abraham_item, mtcd_folder_id, sync_uuid)
                    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                    created = run_bw_json(mtcd_app_dir, ["create", "item"], session=session_mtcd, stdin_data=encoded)
                    mtcd_uuid_map[sync_uuid] = created
                    created_count += 1

        logger.info(f"=== Sync Complete: {created_count} created, {updated_count} updated, {unchanged_count} unchanged ===")

    except Exception as exc:
        logger.error(f"Sync execution failed: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        # Secure cleanup: lock vaults
        if session_mtcd:
            try:
                run_bw_raw(mtcd_app_dir, ["lock"], session=session_mtcd)
            except Exception:
                pass
        if session_abraham:
            try:
                run_bw_raw(abraham_app_dir, ["lock"], session=session_abraham)
            except Exception:
                pass


if __name__ == "__main__":
    main()
