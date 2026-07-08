#!/usr/bin/env python3
"""
Odoo 19 JSON‑RPC script

Purpose:
  * Log in using an API key (username + api_key).
  * Read the quality.issue.log record id=72046.
  * Verify the record is in state "warning" (button visible).
  * Call the server method ``action_check_and_clear`` on that record.
  * Report whether the record still exists afterwards.

Credentials (replace if they change):
    ODOO_URL   = https://staging-odoo19-captivea.odoo.com
    DB_NAME    = captivea-staging-odoo19-33645016
    USERNAME   = divyesh
    API_KEY    = e69028a32e4d039a6ac739349cb4223f3fc5014b
"""

import sys
import json
import uuid
import requests
from urllib.parse import urljoin

# ---------------------------------------------------------------------
# Configuration (edit only if needed)
# ---------------------------------------------------------------------
ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB_NAME  = "captivea-staging-odoo19-33645016"
USERNAME = "sebastien.riss@captivea.com"
API_KEY  = "a,"

MODEL_NAME   = "quality.issue.log"
RECORD_ID    = 72032
EXPECTED_STATE = "warning"
METHOD_NAME    = "action_check_and_clear"

JSONRPC_ENDPOINT = urljoin(ODOO_URL, "/jsonrpc")
HEADERS = {"Content-Type": "application/json"}

# ---------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------

def jsonrpc_call(service: str, method: str, args: list):
    """Perform a generic JSON‑RPC call and return the ``result`` field.
    Raises ``RuntimeError`` on Odoo errors.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": service,
            "method": method,
            "args": args,
        },
        "id": str(uuid.uuid4()),
    }
    resp = requests.post(JSONRPC_ENDPOINT, headers=HEADERS, json=payload)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Odoo error: {data['error']}")
    return data.get("result")

def login() -> int:
    """Authenticate and return the uid.
    For API‑key authentication Odoo expects the API key to be passed as the password.
    """
    uid = jsonrpc_call("common", "login", [DB_NAME, USERNAME, API_KEY])
    if not uid:
        raise RuntimeError("Login returned falsy uid – check credentials.")
    print(f"[INFO] Logged in as uid={uid}")
    return uid

def read_record(uid: int) -> dict:
    fields = ["id", "state"]
    recs = jsonrpc_call(
        "object",
        "execute_kw",
        [
            DB_NAME,
            uid,
            API_KEY,
            MODEL_NAME,
            "read",
            [[RECORD_ID]],
            {"fields": fields},
        ],
    )
    if not recs:
        raise RuntimeError(f"Record {RECORD_ID} not found.")
    return recs[0]

def call_method(uid: int) -> dict:
    # No extra kwargs – only the list of ids.
    return jsonrpc_call(
        "object",
        "execute_kw",
        [
            DB_NAME,
            uid,
            API_KEY,
            MODEL_NAME,
            METHOD_NAME,
            [[RECORD_ID]],
            {},
        ],
    )

def record_exists(uid: int) -> bool:
    """Return ``True`` if the record can be read, ``False`` otherwise.
    Odoo may raise different error structures for a missing record, so we treat
    *any* error that mentions "does not exist" or "Record not found" as a sign that
    the record has been deleted. All other exceptions are re‑raised.
    """
    try:
        jsonrpc_call(
            "object",
            "execute_kw",
            [
                DB_NAME,
                uid,
                API_KEY,
                MODEL_NAME,
                "read",
                [[RECORD_ID]],
                {"fields": ["id"]},
            ],
        )
        return True
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "record not found" in msg:
            return False
        raise

# ---------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------

def main():
    try:
        uid = login()
        rec = read_record(uid)
        cur_state = rec.get("state")
        print(f"[INFO] Record {RECORD_ID} current state: '{cur_state}'")
        if cur_state != EXPECTED_STATE:
            print(f"[WARN] Expected state '{EXPECTED_STATE}'. Button not visible – aborting.")
            sys.exit(0)
        print(f"[INFO] Calling method '{METHOD_NAME}' on the record …")
        result = call_method(uid)
        print("[INFO] Method returned:", json.dumps(result, indent=2))
        exists = record_exists(uid)
        if exists:
            print(f"[RESULT] Record {RECORD_ID} still exists after the call.")
        else:
            print(f"[RESULT] Record {RECORD_ID} has been deleted (expected).")
    except Exception as exc:
        print("[ERROR]", exc)
        sys.exit(1)

if __name__ == "__main__":
    main()
