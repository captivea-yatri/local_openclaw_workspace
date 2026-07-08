#!/usr/bin/env python3
"""Test flow for an existing project (ID 1962) without creating partner, user, sales order, or invoice.
It exercises:
  * Assign an existing domain to the project (if not already assigned)
  * Create an initial phase
  * Create a default role
  * Run the project requirement wizard (action_id 3652) to create a task, falling back to manual creation
  * Create a sub‑task and post chatter messages
  * Produce a JSON report of the actions performed.
"""

import json, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration – edit if your Odoo instance changes
# ---------------------------------------------------------------------------
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Main workflow (project‑only)
# ---------------------------------------------------------------------------
def main():
    uid, models = connect_admin()
    project_id = 1962  # supplied by user
    ts = int(time.time())

    # ---------------------------------------------------
    # Ensure a domain is linked to the project (no creation)
    # ---------------------------------------------------
    existing = models.execute_kw(DB, uid, PASS, "project.domain", "search_read", [[]], {"fields": ["id"], "limit": 1})
    if existing:
        domain_id = existing[0]["id"]
        try:
            models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"default_domain_ids": [(4, domain_id)]}])
            log(f"[+] Assigned existing domain ID={domain_id} to project {project_id}")
        except Exception as e:
            log(f"[!] Could not assign domain: {e}")
    else:
        log("[!] No domain found – skipping domain assignment")
        domain_id = None

    # ---------------------------------------------------
    # Create an initial phase for the project
    # ---------------------------------------------------
    phase_vals = {
        "name": "Initial Phase",
        "project_id": project_id,
        "active": True,
        "sequence": 1,
    }
    phase_id = models.execute_kw(DB, uid, PASS, "project.phase", "create", [phase_vals])
    log(f"[+] Phase created (ID={phase_id})")

    # ---------------------------------------------------
    # Create a default role (used by tasks)
    # ---------------------------------------------------
    role_vals = {"name": "Default Role"}
    role_id = models.execute_kw(DB, uid, PASS, "project.role", "create", [role_vals])
    log(f"[+] Role created (ID={role_id})")

    # ---------------------------------------------------
    # Try to create a task via the wizard (action_id 3652)
    # ---------------------------------------------------
    ctx = {"active_model": "project.project", "active_id": project_id, "action_id": 3652}
    wizard_vals = {"project_id": project_id, "phase_id": phase_id}
    wizard_id = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "create", [wizard_vals], {"context": ctx})
    log(f"[+] Wizard record created (ID={wizard_id})")
    # Ensure phase_id is set on the wizard (the wizard only exposes this field)
    try:
        models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "write", [[wizard_id], {"phase_id": phase_id}])
    except Exception as e:
        log(f"[!] Failed to set phase_id on wizard: {e}")
    wizard_success = False
    try:
        models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "action_create_task_from_project", [wizard_id], {"context": ctx})
        log("[+] Wizard action executed – task created via wizard (may return None).")
        wizard_success = True
    except Exception as e:
        log(f"[!] Wizard action failed: {e}")

    # ---------------------------------------------------
    # Retrieve the newly created task (if wizard succeeded)
    # ---------------------------------------------------
    task_id = None
    if wizard_success:
        tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "order": "id desc", "limit": 1})
        if tasks:
            task_id = tasks[0]["id"]
            log(f"[+] Task found via wizard (ID={task_id})")
    # ---------------------------------------------------
    # Fallback manual task creation if needed
    # ---------------------------------------------------
    if not task_id:
        task_vals = {
            "name": f"Manual task {ts}",
            "project_id": project_id,
            "default_phase_id": phase_id,
            "default_domain_id": domain_id,
        }
        task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
        log(f"[+] Manual task created (ID={task_id})")

    # ---------------------------------------------------
    # Create a sub‑task linked to the main task
    # ---------------------------------------------------
    subtask_vals = {
        "name": f"Sub‑task {ts}",
        "project_id": project_id,
        "parent_id": task_id,
    }
    subtask_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [subtask_vals])
    log(f"[+] Sub‑task created (ID={subtask_id})")

    # ---------------------------------------------------
    # Post a chatter message on the sub‑task (simulating portal side)
    # ---------------------------------------------------
    try:
        models.execute_kw(DB, uid, PASS, "project.task", "message_post", [[subtask_id], {"body": "Test message from automation"}])
        log("[+] Chatter message posted on sub‑task")
    except Exception as e:
        log(f"[!] Failed to post chatter message: {e}")

    # ---------------------------------------------------
    # Build report
    # ---------------------------------------------------
    report = {
        "timestamp": ts,
        "project_id": project_id,
        "phase_id": phase_id,
        "domain_id": domain_id,
        "role_id": role_id,
        "task_id": task_id,
        "subtask_id": subtask_id,
    }
    report_path = "test_project_flow_1962_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
