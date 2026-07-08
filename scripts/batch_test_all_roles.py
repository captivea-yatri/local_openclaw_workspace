#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility to run test_access_rights_roles_rpc.py for *every* role in the database,
one at a time, with a small pause between runs. This works around the ngrok
rate‑limit / connection‑drop issue that occurs when the original script tries to
assign many roles sequentially in a single long‑running process.

Usage (run from the workspace root)::

    python3 scripts/batch_test_all_roles.py

The script will:
  1. Authenticate as the admin user supplied via the constants below.
  2. Pull the list of role names from the DB.
  3. For each role it will invoke the main test script with that single role
     (``--roles "<role_name>"``) and write the JSON report to
     ``/tmp/access_breaks_<safe_role>.json``.
  4. Sleep 2 seconds between runs to give ngrok a breather.
"""
import json
import os
import shlex
import subprocess
import sys
import time
from xmlrpc.client import ServerProxy

# ---------------------------------------------------------------------------
# Configuration – adjust if your credentials change
# ---------------------------------------------------------------------------
URL = "https://dc0a-2402-a00-152-5177-6488-2dd3-77c7-af1b.ngrok-free.app"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"

SCRIPT = os.path.abspath("scripts/test_access_rights_roles_rpc.py")
PYTHON = sys.executable

def safe_role_name(name: str) -> str:
    """Return a filesystem‑safe version of a role name (no spaces, no quotes)."""
    return "".join(c if c.isalnum() else "_" for c in name)

def main():
    # Authenticate via XML‑RPC (simpler for this small call)
    common = ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("[ERROR] authentication failed")
        sys.exit(1)
    models = ServerProxy(f"{URL}/xmlrpc/2/object")
    role_ids = models.execute_kw(DB, uid, PASSWORD, "res.users.role", "search", [[]], {"order": "name"})
    roles = models.execute_kw(DB, uid, PASSWORD, "res.users.role", "read", [role_ids, ["name"]])
    print(f"[INFO] Found {len(roles)} roles")

    for r in roles:
        role_name = r["name"]
        safe_name = safe_role_name(role_name)
        out_file = f"/tmp/access_breaks_{safe_name}.json"
        cmd = [PYTHON, SCRIPT,
               "--url", URL,
               "--db", DB,
               "--user", USER,
               "--password", PASSWORD,
               "--roles", role_name,
               "--report-file", out_file]
        print(f"[RUN] Testing role: {role_name!r} -> {out_file}")
        try:
            # Run synchronously – let it finish before the next role.
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Role {role_name!r} failed (exit {e.returncode})")
        # Small pause to avoid ngrok throttling
        time.sleep(2)

if __name__ == "__main__":
    main()
