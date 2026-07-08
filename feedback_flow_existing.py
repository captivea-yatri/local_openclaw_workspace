#!/usr/bin/env python3
"""Feedback flow using an existing project (ID 2904) and its portal user.

Steps:
1️⃣ Retrieve the project (ID 2904) and its partner.
2️⃣ Find a portal user (share=True) linked to that partner.
3️⃣ Create a `project.feedback` record as that portal user.
4️⃣ Backend updates extra fields (status).
5️⃣ Convert the feedback into a task via `transform_feedback_into_task` if available;
   otherwise fallback to manual task creation and link via `task_id`.
6️⃣ Output a JSON report with all relevant IDs.
"""

import json, sys, time, ssl, xmlrpc.client
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration – adjust if your Odoo instance changes
# ---------------------------------------------------------------------------
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

PROJECT_ID = 2904  # <-- existing project to use

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def log(msg):
    print(msg)

def find_portal_group(models, uid):
    groups = models.execute_kw(
        DB, uid, PASS, "res.groups", "search_read",
        [[("name", "=", "Portal")]],
        {"fields": ["id"], "limit": 1}
    )
    return groups[0]["id"] if groups else None

def connect(user, password):
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, user, password, {})
    if not uid:
        raise RuntimeError(f"Authentication failed for {user}")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

def find_portal_user(models, uid, partner_id):
    # Search portal users (share=True) with the given partner_id
    users = models.execute_kw(
        DB, uid, PASS, "res.users", "search_read",
        [[("share", "=", True), ("partner_id", "=", partner_id)]],
        {"fields": ["id"], "limit": 1}
    )
    return users[0]["id"] if users else None

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main():
    uid, models = connect(ADMIN, PASS)
    ts = int(time.time())

    # 1️⃣ Load the existing project and its partner
    project = models.execute_kw(DB, uid, PASS, "project.project", "read", [[PROJECT_ID]], {"fields": ["partner_id"]})[0]
    partner_id = project.get("partner_id")
    if not partner_id:
        raise RuntimeError(f"Project {PROJECT_ID} has no partner_id")
    partner_id = partner_id[0] if isinstance(partner_id, (list, tuple)) else partner_id
    log(f"[+] Project {PROJECT_ID} uses partner {partner_id}")

    # 2️⃣ Find a portal user linked to this partner
    portal_user_id = find_portal_user(models, uid, partner_id)
    if not portal_user_id:
        # No portal user exists – create one for this partner.
        # Retrieve partner's email (fallback to a generated one).
        partner_data = models.execute_kw(DB, uid, PASS, "res.partner", "read", [[partner_id]], {"fields": ["email", "name"]})[0]
        email = partner_data.get("email") or f"portal_{partner_id}@example.com"
        portal_user_vals = {
            "login": email,
            "partner_id": partner_id,
            "password": "a",
            "share": True,
        }
        # Assign portal group if it exists.
        portal_group_id = find_portal_group(models, uid)
        if portal_group_id:
            portal_user_vals["group_ids"] = [(6, 0, [portal_group_id])]
        else:
            portal_user_vals["group_ids"] = [(5,)]
        try:
            portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
            log(f"[+] Created portal user (UID={portal_user_id}) for partner {partner_id}")
        except Exception as e:
            # Likely duplicate login – find existing user by login
            log(f"[!] Portal user creation failed ({e}); trying to locate existing user.")
            existing = models.execute_kw(DB, uid, PASS, "res.users", "search_read", [[("login", "=", email)]], {"fields": ["id"], "limit": 1})
            if existing:
                portal_user_id = existing[0]["id"]
                log(f"[+] Reusing existing portal user (UID={portal_user_id}) for partner {partner_id}")
            else:
                raise RuntimeError(f"Could not create or find portal user for login {email}")
    else:
        log(f"[+] Portal user found (UID={portal_user_id})")

    # 3️⃣ Simulate portal login
    # Retrieve the portal user's login/email (needed for auth)
    portal_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[portal_user_id]], {"fields": ["login"]})[0]
    portal_login = portal_user.get("login")
    portal_uid, portal_models = connect(portal_login, "a")  # password is assumed to be "a"

    # 4️⃣ Create feedback as the portal user
    feedback_vals = {
        "name": f"Feedback {ts}",
        "project_id": PROJECT_ID,
        "description": "Automated feedback from portal user (test flow)",
    }
    feedback_id = portal_models.execute_kw(DB, portal_uid, PASS, "project.feedback", "create", [feedback_vals])
    log(f"[+] Feedback created (ID={feedback_id})")

    # 5️⃣ Backend updates extra fields (status)
    extra_vals = {"status": "new"}
    models.execute_kw(DB, uid, PASS, "project.feedback", "write", [[feedback_id], extra_vals])
    log("[+] Feedback status set to 'new'")

    # 6️⃣ Convert feedback → task
    task_id = None
    try:
        result = models.execute_kw(DB, uid, PASS, "project.feedback", "transform_feedback_into_task", [feedback_id])
        if isinstance(result, int):
            task_id = result
        elif isinstance(result, dict) and result.get("task_id"):
            task_id = result["task_id"]
        log(f"[+] Feedback transformed via method – task ID={task_id}")
    except Exception as e:
        log(f"[!] transform_feedback_into_task failed: {e}")

    if not task_id:
        # Fallback: create a task manually and link it
        task_vals = {
            "name": f"Task from feedback {feedback_id}",
            "project_id": PROJECT_ID,
        }
        task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
        log(f"[+] Manual task created (ID={task_id})")
        models.execute_kw(DB, uid, PASS, "project.feedback", "write", [[feedback_id], {"task_id": task_id}])
        log("[+] feedback.task_id linked to created task")

    # -------------------------------------------------
    # 7️⃣ Build final report
    # -------------------------------------------------
    report = {
        "timestamp": ts,
        "project_id": PROJECT_ID,
        "partner_id": partner_id,
        "portal_user_id": portal_user_id,
        "feedback_id": feedback_id,
        "task_id": task_id,
    }
    report_path = "feedback_flow_existing_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
