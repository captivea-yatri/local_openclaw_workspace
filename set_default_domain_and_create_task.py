#!/usr/bin/env python3
"""Utility to set a default domain on an existing project (ID 2904),
create a task leveraging that domain, and execute a server action (ID 3652).
All operations run as the admin user.
"""

import json, sys, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

# Configuration – adjust if the Odoo instance changes
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def log(msg):
    print(msg)

def connect_admin():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

PROJECT_ID = 2904
ACTION_ID = 3652

def main():
    uid, models = connect_admin()
    # -----------------------------------------------------------------
    # 1️⃣ Find a usable domain (any existing domain the admin can read)
    # -----------------------------------------------------------------
    domains = models.execute_kw(DB, uid, PASS, "project.domain", "search_read", [[]], {"fields": ["id"], "limit": 1})
    if not domains:
        log("[!] No project.domain records found – cannot set default domain.")
        sys.exit(1)
    domain_id = domains[0]["id"]
    log(f"[+] Using domain ID={domain_id} as default domain.")

    # -----------------------------------------------------------------
    # 2️⃣ Assign this domain to the project via many2many field default_domain_ids
    # -----------------------------------------------------------------
    try:
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[PROJECT_ID], {"default_domain_ids": [(4, domain_id)]}])
        log(f"[+] default_domain_ids set on project {PROJECT_ID} (domain ID={domain_id}).")
    except Exception as e:
        log(f"[!] Failed to set default_domain_ids on project: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 3️⃣ Create a task inside the project, using the default domain
    # -----------------------------------------------------------------
    # Detect the correct assignee field (custom or standard)
    fields = models.execute_kw(DB, uid, PASS, "project.task", "fields_get", [], {"attributes": ["type"]})
    assignee_field = "x_default_user_id" if "x_default_user_id" in fields else "user_id"

    task_vals = {
        "name": f"Auto‑generated task {int(time.time())}",
        "project_id": PROJECT_ID,
        assignee_field: uid,  # assign to admin for simplicity
        "default_domain_id": domain_id,
    }
    task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
    log(f"[+] Task created (ID={task_id}) linked to project {PROJECT_ID}.")

    # -----------------------------------------------------------------
    # 4️⃣ Execute the server action (ID 3652)
    # -----------------------------------------------------------------
    try:
        # "ir.actions.server" provides a ``run`` method that accepts the action ID.
        models.execute_kw(DB, uid, PASS, "ir.actions.server", "run", [ACTION_ID])
        log(f"[+] Executed server action ID={ACTION_ID}.")
    except Exception as e:
        log(f"[!] Failed to execute action {ACTION_ID}: {e}")

if __name__ == "__main__":
    main()
