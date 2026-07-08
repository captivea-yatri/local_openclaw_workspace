#!/usr/bin/env python3
"""Test workflow:
1️⃣ As admin, locate the project (ID 2904) and its latest task.
2️⃣ Find a portal‑only user (share=True) and authenticate as that user.
3️⃣ Using the portal user, create a **sub‑task** under the latest task (parent_id).
4️⃣ Post a chatter message from the portal user on the sub‑task.
5️⃣ Switch back to admin and verify the sub‑task and its chatter exist.
All actions run via XML‑RPC (SSL verification disabled).
"""

import ssl, xmlrpc.client, json, sys, time
from urllib.parse import urljoin

# ---------------------------------------------------------------------
# Configuration – adjust if the Odoo instance changes
# ---------------------------------------------------------------------
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

def log(msg):
    print(msg)

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

def main():
    # -----------------------------------------------------------------
    # 1️⃣ Admin side – locate project and latest task
    # -----------------------------------------------------------------
    admin_uid, admin_models = connect(ADMIN, PASS)
    PROJECT_ID = 2904

    # Get the most recent task on the project (could be the one created by wizard/manual)
    tasks = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "search_read",
        [[("project_id", "=", PROJECT_ID)]],
        {"fields": ["id", "name"], "order": "id desc", "limit": 1}
    )
    if not tasks:
        log("[!] No existing task found on project – cannot create sub‑task.")
        sys.exit(1)
    parent_task_id = tasks[0]["id"]
    log(f"[+] Parent task found (ID={parent_task_id})")

    # -----------------------------------------------------------------
    # 2️⃣ Find a portal‑only user (share=True) and get its login/password
    # -----------------------------------------------------------------
    portal_users = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "res.users", "search_read",
        [[("share", "=", True)]],
        {"fields": ["id", "login"], "limit": 1}
    )
    if not portal_users:
        log("[!] No portal user found – cannot continue.")
        sys.exit(1)
    portal_user = portal_users[0]
    portal_login = portal_user["login"]
    portal_password = "a"  # we know the password used when creating the user
    log(f"[+] Portal user selected: login={portal_login}, uid={portal_user['id']}")

    # -----------------------------------------------------------------
    # 3️⃣ Authenticate as the portal user
    # -----------------------------------------------------------------
    # Ensure the portal user has a known password before auth (admin can set it)
    try:
        admin_models.execute_kw(DB, admin_uid, PASS, "res.users", "write", [[portal_user["id"], {"password": portal_password}]])
        log(f"[+] Set portal user password to known value for login.")
    except Exception as e:
        log(f"[!] Could not set portal user password: {e}")
    portal_uid, portal_models = connect(portal_login, portal_password)

    # -----------------------------------------------------------------
    # 4️⃣ Portal user creates a sub‑task under the parent task
    # -----------------------------------------------------------------
    subtask_name = f"Portal sub‑task {int(time.time())}"
    subtask_vals = {
        "name": subtask_name,
        "project_id": PROJECT_ID,
        "parent_id": parent_task_id,
        # assign to the portal user itself (field may be custom)
    }
    try:
        subtask_id = portal_models.execute_kw(
            DB, portal_uid, PASS,
            "project.task", "create", [subtask_vals]
        )
        log(f"[+] Sub‑task created by portal user (ID={subtask_id})")
    except Exception as e:
        log(f"[!] Failed to create sub‑task as portal user: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 5️⃣ Portal user posts a chatter message on the sub‑task
    # -----------------------------------------------------------------
    message_body = "Test message from portal user – verification of chatter communication."
    try:
        portal_models.execute_kw(
            DB, portal_uid, PASS,
            "project.task", "message_post", [subtask_id], {"body": message_body}
        )
        log("[+] Chatter message posted on sub‑task (portal side).")
    except Exception as e:
        log(f"[!] Failed to post chatter message: {e}")
        # continue – we still want admin verification of the task itself

    # -----------------------------------------------------------------
    # 6️⃣ Admin side – verify sub‑task existence and retrieve its messages
    # -----------------------------------------------------------------
    subtask = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "read", [[subtask_id]],
        {"fields": ["id", "name", "parent_id", "message_ids"]}
    )[0]
    log(f"[+] Admin verified sub‑task: {subtask}")

    # Retrieve chatter messages (mail.message) linked to the sub‑task
    if subtask.get("message_ids"):
        msgs = admin_models.execute_kw(
            DB, admin_uid, PASS,
            "mail.message", "read", [subtask["message_ids"]],
            {"fields": ["id", "body", "author_id"]}
        )
        log(f"[+] Retrieved {len(msgs)} chatter message(s) on the sub‑task.")
        # Show author names for clarity
        authors = admin_models.execute_kw(
            DB, admin_uid, PASS,
            "res.users", "read", [[msg["author_id"][0] for msg in msgs]],
            {"fields": ["id", "login"]}
        )
        log(f"    Authors of messages: {[a['login'] for a in authors]}")
    else:
        log("[!] No chatter messages found on the sub‑task.")

    # -----------------------------------------------------------------
    # 7️⃣ Build verification report
    # -----------------------------------------------------------------
    report = {
        "timestamp": int(time.time()),
        "project_id": PROJECT_ID,
        "parent_task_id": parent_task_id,
        "subtask_id": subtask_id,
        "subtask_name": subtask_name,
        "portal_user_login": portal_login,
        "chatter_message_body": message_body,
        "admin_view": subtask,
    }
    report_path = "portal_subtask_flow_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
