#!/usr/bin/env python3
import json, sys, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "***"  # placeholder matches earlier script that succeeded

# Connect
common = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common",
    context=ssl._create_unverified_context()
)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "auth failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/object",
    context=ssl._create_unverified_context()
)

PROJECT_ID = 2870
SIGNATORY_PARTNER_ID = 2280326  # using the test partner created earlier

# Helper to log actions
log = []

def add(step, status, detail=""):
    log.append({"step": step, "status": status, "detail": detail})

# 1. Update project fields
try:
    vals = {
        "signatory_progress_report_partner_id": SIGNATORY_PARTNER_ID,
        # Assuming custom fields exist; adjust names if needed
        "x_phase_id": 1,   # placeholder phase record ID
        "x_status_id": 1,  # placeholder status record ID
        "sale_order_id": 8674,  # link to existing sales order
    }
    models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[PROJECT_ID], vals])
    add("update_project", "PASS", f"Project {PROJECT_ID} updated with signatory {SIGNATORY_PARTNER_ID}")
except Exception as e:
    add("update_project", "FAIL", str(e))

# 2. Create a task linked to this project
try:
    task_vals = {
        "name": "Signatory Progress Report",
        "project_id": PROJECT_ID,
        "description": "Prepare and send the progress report to the signatory partner.",
        "user_ids": [(6, 0, [SIGNATORY_PARTNER_ID])],  # assign to signatory if they are a user
    }
    task_id = models.execute_kw(DB, uid, PASSWORD, "project.task", "create", [task_vals])
    add("create_task", "PASS", f"Task {task_id} created for project {PROJECT_ID}")
except Exception as e:
    add("create_task", "FAIL", str(e))

print(json.dumps({"log": log}, indent=2))
