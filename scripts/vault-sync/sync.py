#!/usr/bin/env python3
"""
Vaultwarden Multi-Instance Dual-Channel Sync Bridge (MTCD <-> Abraham)
Preserves TOTP (2FA seeds) and Passkeys (FIDO2 credentials).

Channels:
  Channel 1: MTCD ('Sync to Abraham')  <---> Abraham ('Sync from MTCD')
  Channel 2: Abraham ('Sync to MTCD')  <---> MTCD ('Sync from Abraham')

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

ABRAHAM_URL = os.getenv("ABRAHAM_URL", "https://pw.abraham16.com").rstrip("/")
ABRAHAM_EMAIL = os.getenv("ABRAHAM_EMAIL", "ben@abraham16.com")
ABRAHAM_CLIENT_ID = os.getenv("ABRAHAM_CLIENT_ID", "")
ABRAHAM_CLIENT_SECRET = os.getenv("ABRAHAM_CLIENT_SECRET", "")
ABRAHAM_PASSWORD = os.getenv("ABRAHAM_PASSWORD", "")

# Dual-channel folder configuration
# Channel 1: MTCD -> Abraham
MTCD_OUTBOUND_FOLDER = os.getenv("MTCD_OUTBOUND_FOLDER", "Sync to Abraham")
ABRAHAM_INBOUND_FOLDER = os.getenv("ABRAHAM_INBOUND_FOLDER", "Sync from MTCD")

# Channel 2: Abraham -> MTCD
ABRAHAM_OUTBOUND_FOLDER = os.getenv("ABRAHAM_OUTBOUND_FOLDER", "Sync to MTCD")
MTCD_INBOUND_FOLDER = os.getenv("MTCD_INBOUND_FOLDER", "Sync from Abraham")

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


def get_or_create_folder(name, app_dir, session, folder_name):
    """Get folder by name, automatically creating it if missing."""
    folders = run_bw_json(app_dir, ["list", "folders"], session=session) or []
    for f in folders:
        if f.get("name", "").strip().lower() == folder_name.strip().lower():
            return f["id"]

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

    # Filter out internal sync tracking fields from original fields
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


def sync_channel(
    channel_name,
    src_name, src_dir, src_session, src_folder_name,
    dst_name, dst_dir, dst_session, dst_folder_name
):
    """Synchronize a directional channel between two folders with bidirectional updates."""
    logger.info(f"--- Channel: {channel_name} [{src_name}: '{src_folder_name}' <---> {dst_name}: '{dst_folder_name}'] ---")

    src_folder_id = get_or_create_folder(src_name, src_dir, src_session, src_folder_name)
    dst_folder_id = get_or_create_folder(dst_name, dst_dir, dst_session, dst_folder_name)

    src_items = run_bw_json(src_dir, ["list", "items", "--folderid", src_folder_id], session=src_session) or []
    dst_items = run_bw_json(dst_dir, ["list", "items", "--folderid", dst_folder_id], session=dst_session) or []

    logger.info(f"Items in {src_name} ('{src_folder_name}'): {len(src_items)}")
    logger.info(f"Items in {dst_name} ('{dst_folder_name}'): {len(dst_items)}")

    # Index destination items by _sync_uuid and by (name, username) fallback
    dst_uuid_map = {}
    dst_name_map = {}
    for item in dst_items:
        u = get_sync_uuid(item)
        if u:
            dst_uuid_map[u] = item
        uname = (item.get("login") or {}).get("username") or ""
        key = (item.get("name", "").strip().lower(), uname.strip().lower())
        dst_name_map[key] = item

    src_uuid_map = {}
    for item in src_items:
        u = get_sync_uuid(item)
        if u:
            src_uuid_map[u] = item

    created = 0
    updated = 0
    unchanged = 0

    # 1. Forward Sync: Source -> Destination
    for src_item in src_items:
        item_name = src_item.get("name", "Unknown")
        sync_uuid = get_sync_uuid(src_item)

        if not sync_uuid:
            uname = (src_item.get("login") or {}).get("username") or ""
            fallback_key = (src_item.get("name", "").strip().lower(), uname.strip().lower())
            if fallback_key in dst_name_map:
                matched = dst_name_map[fallback_key]
                sync_uuid = get_sync_uuid(matched) or str(uuid.uuid4())
            else:
                sync_uuid = str(uuid.uuid4())

            logger.info(f"[{channel_name}] Assigning _sync_uuid [{sync_uuid}] to {src_name} item '{item_name}'")
            src_item = set_sync_uuid(src_dir, src_session, src_item, sync_uuid)
            src_uuid_map[sync_uuid] = src_item

        dst_match = dst_uuid_map.get(sync_uuid)
        if not dst_match:
            uname = (src_item.get("login") or {}).get("username") or ""
            fallback_key = (src_item.get("name", "").strip().lower(), uname.strip().lower())
            dst_match = dst_name_map.get(fallback_key)

        if not dst_match:
            # Create in destination
            passkeys = len((src_item.get("login") or {}).get("fido2Credentials", []))
            has_totp = bool((src_item.get("login") or {}).get("totp"))
            logger.info(f"[{channel_name}] CREATE -> {dst_name}: '{item_name}' (Passkeys: {passkeys}, OTP: {'Yes' if has_totp else 'No'})")
            payload = build_sync_payload(src_item, dst_folder_id, sync_uuid)
            encoded = base64.b64encode(json.dumps(payload).encode()).decode()
            created_item = run_bw_json(dst_dir, ["create", "item"], session=dst_session, stdin_data=encoded)
            dst_uuid_map[sync_uuid] = created_item
            created += 1
        else:
            # Existing item: compare revision dates
            src_rev = isoparse(src_item["revisionDate"])
            dst_rev = isoparse(dst_match["revisionDate"])

            if src_rev > dst_rev:
                logger.info(f"[{channel_name}] UPDATE -> {dst_name}: '{item_name}' ({src_name} is newer)")
                payload = build_sync_payload(src_item, dst_folder_id, sync_uuid)
                payload["id"] = dst_match["id"]
                encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                run_bw_json(dst_dir, ["edit", "item", dst_match["id"]], session=dst_session, stdin_data=encoded)
                updated += 1
            elif dst_rev > src_rev:
                logger.info(f"[{channel_name}] UPDATE -> {src_name}: '{item_name}' ({dst_name} is newer)")
                payload = build_sync_payload(dst_match, src_folder_id, sync_uuid)
                payload["id"] = src_item["id"]
                encoded = base64.b64encode(json.dumps(payload).encode()).decode()
                run_bw_json(src_dir, ["edit", "item", src_item["id"]], session=src_session, stdin_data=encoded)
                updated += 1
            else:
                unchanged += 1

    # 2. Reverse Sync for items placed directly in the destination folder
    for dst_item in dst_items:
        sync_uuid = get_sync_uuid(dst_item)
        item_name = dst_item.get("name", "Unknown")
        if sync_uuid and sync_uuid not in src_uuid_map:
            logger.info(f"[{channel_name}] CREATE -> {src_name}: '{item_name}' (Reverse synced from {dst_name})")
            payload = build_sync_payload(dst_item, src_folder_id, sync_uuid)
            encoded = base64.b64encode(json.dumps(payload).encode()).decode()
            created_item = run_bw_json(src_dir, ["create", "item"], session=src_session, stdin_data=encoded)
            src_uuid_map[sync_uuid] = created_item
            created += 1

    logger.info(f"[{channel_name}] Results: {created} created, {updated} updated, {unchanged} unchanged")
    return created, updated, unchanged


def main():
    validate_config()

    mtcd_app_dir = os.path.join(DATA_ROOT, "mtcd")
    abraham_app_dir = os.path.join(DATA_ROOT, "abraham")

    logger.info("=== Starting Vaultwarden Multi-Instance Dual-Channel Sync ===")
    logger.info(f"Channel 1: MTCD '{MTCD_OUTBOUND_FOLDER}' <---> Abraham '{ABRAHAM_INBOUND_FOLDER}'")
    logger.info(f"Channel 2: Abraham '{ABRAHAM_OUTBOUND_FOLDER}' <---> MTCD '{MTCD_INBOUND_FOLDER}'")

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

        total_created = 0
        total_updated = 0
        total_unchanged = 0

        # Channel 1: MTCD Outbound ('Sync to Abraham') -> Abraham Inbound ('Sync from MTCD')
        c1, u1, nc1 = sync_channel(
            "MTCD->Abraham",
            "MTCD", mtcd_app_dir, session_mtcd, MTCD_OUTBOUND_FOLDER,
            "Abraham", abraham_app_dir, session_abraham, ABRAHAM_INBOUND_FOLDER
        )
        total_created += c1
        total_updated += u1
        total_unchanged += nc1

        # Channel 2: Abraham Outbound ('Sync to MTCD') -> MTCD Inbound ('Sync from Abraham')
        c2, u2, nc2 = sync_channel(
            "Abraham->MTCD",
            "Abraham", abraham_app_dir, session_abraham, ABRAHAM_OUTBOUND_FOLDER,
            "MTCD", mtcd_app_dir, session_mtcd, MTCD_INBOUND_FOLDER
        )
        total_created += c2
        total_updated += u2
        total_unchanged += nc2

        logger.info(f"=== All Channels Complete: {total_created} created, {total_updated} updated, {total_unchanged} unchanged ===")

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
