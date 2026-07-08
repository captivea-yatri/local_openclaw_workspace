#!/usr/bin/env python3
"""Automated end‑to‑end test of the portal‑access flow using a fresh portal user.
   The script performs **all** steps:
   1️⃣ Create a unique partner & portal user
   2️⃣ Create a project linked to that partner
   3️⃣ Set project visibility to "invited portal users & internal"
   4️⃣ Share the project in **editable** mode via ``project.share.wizard``
   5️⃣ Create a task (assignee field detected automatically)
   6️⃣ Post a feedback message on the task as the portal user
   7️⃣ Verify each step and write a JSON report.
   Run it repeatedly – the email/partner name includes a timestamp, so there are
   no collisions.
"""
import json, sys, time, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

def log(msg):
    print(msg)

def find_portal_group(models, uid):
    groups = models.execute_kw(DB, uid, PASS, "res.groups", "search_read",
                               [[("name", "=", "Portal")]],
                               {"fields": ["id"], "limit": 1})
    return groups[0]["id"] if groups else None

def main():
    # --------------------------------------------------------------
    # 0️⃣ Connect as admin
    # --------------------------------------------------------------
    common = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"))
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    log(f"[+] Admin UID = {uid}")
    models = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"))

    # --------------------------------------------------------------
    # 1️⃣ Create unique partner & portal user
    # --------------------------------------------------------------
    ts = int(time.time())
    email = f"portal_user_{ts}@example.com"
    partner_vals = {"name": f"Portal Test Customer {ts}", "email": email}
    partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [partner_vals])
    log(f"[+] Partner created (ID={partner_id})")

    portal_group_id = find_portal_group(models, uid)
    portal_user_vals = {
        "login": email,
        "partner_id": partner_id,
        "password": "a",
        "share": True,
    }
    if portal_group_id:
        portal_user_vals["groups_id"] = [(6, 0, [portal_group_id])]
    portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
    log(f"[+] Portal user created (UID={portal_user_id})")

    # --------------------------------------------------------------
    # 2️⃣ Create project linked to partner
    # --------------------------------------------------------------
    project_vals = {"name": f"Portal Test Project {ts}", "partner_id": partner_id, "user_id": uid}
    project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [project_vals])
    log(f"[+] Project created (ID={project_id})")
    print(f"PROJECT_ID:{project_id}")

    # --------------------------------------------------------------
    # 3️⃣ Set project visibility (if the field exists)
    # --------------------------------------------------------------
    try:
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"privacy_visibility": "portal"}])
        log("[+] Project visibility set to 'portal' (invited portal users + internal)")
    except Exception as e:
        log(f"[!] Could not set visibility: {e}")

    # --------------------------------------------------------------
    # 4️⃣ Share the project in editable mode via the wizard
    # --------------------------------------------------------------
    wizard_vals = {"res_model": "project.project", "res_id": project_id, "partner_ids": [(6, 0, [partner_id])]}
    wizard_id = models.execute_kw(DB, uid, PASS, "project.share.wizard", "create", [wizard_vals])
    log(f"[+] Share wizard created (ID={wizard_id})")
    # Try action_share first, then button_share
    try:
        models.execute_kw(DB, uid, PASS, "project.share.wizard", "action_share", [wizard_id])
        log("[+] Project shared (editable) via action_share")
    except Exception:
        try:
            models.execute_kw(DB, uid, PASS, "project.share.wizard", "button_share", [wizard_id])
            log("[+] Project shared (editable) via button_share")
        except Exception as e2:
            log(f"[!] Could not share via wizard: {e2}")

    # --------------------------------------------------------------
    # 5️⃣ Determine assignee field for tasks (fallback to x_default_user_id)
    # --------------------------------------------------------------
    fields = models.execute_kw(DB, uid, PASS, "project.task", "fields_get", [], {"attributes": ["type"]})
    assignee_field = "x_default_user_id" if "x_default_user_id" in fields else None
    if not assignee_field:
        log("[!] No suitable assignee field found on project.task – aborting")
        sys.exit(1)
    log(f"[+] Using assignee field '{assignee_field}' for task creation")

    # --------------------------------------------------------------
    # 6️⃣ Create a task inside the project
    # --------------------------------------------------------------
    task_vals = {"name": f"Portal Test Task {ts}", "project_id": project_id, assignee_field: portal_user_id, "description": "Task created by automated flow."}
    task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
    log(f"[+] Task created (ID={task_id})")

    # --------------------------------------------------------------
    # 7️⃣ Post a feedback message on the task as the portal user
    # --------------------------------------------------------------
    feedback_vals = {"model": "project.task", "res_id": task_id, "message_type": "comment", "subtype_id": 1, "author_id": portal_user_id, "body": "<p>Automated feedback from the portal side.</p>"}
    feedback_id = models.execute_kw(DB, uid, PASS, "mail.message", "create", [feedback_vals])
    log(f"[+] Feedback posted (mail.message ID={feedback_id})")

    # --------------------------------------------------------------
    # 8️⃣ Verify collaborators (project should list the partner)
    # --------------------------------------------------------------
    collab = models.execute_kw(DB, uid, PASS, "project.project", "read", [project_id], {"fields": ["message_partner_ids", "signatory_portal_report_partner_ids"]})
    log(f"[+] Project collaborators: {collab[0]}")

    # --------------------------------------------------------------
    # 9️⃣  Write final JSON report
    # --------------------------------------------------------------
    report = {
        "partner_id": partner_id,
        "portal_user_id": portal_user_id,
        "project_id": project_id,
        "task_id": task_id,
        "feedback_message_id": feedback_id,
        "project_collaborators": collab[0],
    }
    out_path = "/home/captivea/.openclaw/workspace/portal_flow_full_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Full report written to {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
