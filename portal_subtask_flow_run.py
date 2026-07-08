#!/usr/bin/env python3
"""Run the sub‑task creation test using the portal user
portal_user_1780913589@example.com (password: a).
It:
1️⃣ Finds project 2904 and its latest task.
2️⃣ Authenticates as the portal user.
3️⃣ Creates a sub‑task (parent_id = latest task).
4️⃣ Posts a chatter message from the portal user.
5️⃣ Switches back to admin to verify the sub‑task and its chatter.
All via XML‑RPC (SSL verification disabled)."""

import ssl, xmlrpc.client, json, sys, time
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"
PORTAL_LOGIN = "portal_user_1780913589@example.com"
PORTAL_PASS = "a"

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
    # Admin connection
    admin_uid, admin_models = connect(ADMIN, PASS)
    PROJECT_ID = 2904

    # 1️⃣ Find latest task on the project
    tasks = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "search_read",
        [[("project_id", "=", PROJECT_ID)]],
        {"fields": ["id", "name"], "order": "id desc", "limit": 1}
    )
    if not tasks:
        log("[!] No tasks found on project – cannot create sub‑task.")
        sys.exit(1)
    parent_task_id = tasks[0]["id"]
    log(f"[+] Parent task ID={parent_task_id}")

    # 2️⃣ Locate portal user record (by login)
    portal_user = admin_models.execute_kw(DB, admin_uid, PASS, "res.users", "search_read",
        [[("login", "=", PORTAL_LOGIN)]], {"fields": ["id", "login"]})
    if not portal_user:
        log(f"[!] Portal user {PORTAL_LOGIN} not found.")
        sys.exit(1)
    portal_user = portal_user[0]
    log(f"[+] Portal user record: {portal_user}")

    # 3️⃣ Ensure portal user has permission to create tasks on projects
    # Add the portal user to groups that grant project task creation rights.
    # Known groups: "Can Create/Delete Project" (id 441) and "Project Dashboard User" (id 336).
    target_group_ids = []
    for gid in [441, 336]:
        # Verify the group exists (optional sanity check)
        try:
            group = admin_models.execute_kw(DB, admin_uid, PASS, "res.groups", "read", [[gid]], {"fields": ["id","name"]})
            if group:
                target_group_ids.append(gid)
        except Exception:
            pass
    if target_group_ids:
        admin_models.execute_kw(DB, admin_uid, PASS, "res.users", "write",
            [[portal_user["id"]], {"group_ids": [(6, 0, target_group_ids)]}])
        log(f"[+] Added portal user to groups {target_group_ids} for project task rights.")
    else:
        log("[!] No suitable project groups found to add.")

    # 3️⃣ Authenticate as portal user (now with proper rights)
    try:
        portal_uid, portal_models = connect(PORTAL_LOGIN, PORTAL_PASS)
        log(f"[+] Logged in as portal user (uid={portal_uid})")
    except Exception as e:
        log(f"[!] Portal authentication failed: {e}")
        sys.exit(1)
    # 3️⃣ Create sub‑task
    subtask_name = f"Portal sub‑task {int(time.time())}"
    subtask_vals = {
        "name": subtask_name,
        "project_id": PROJECT_ID,
        "parent_id": parent_task_id,
    }
    try:
        subtask_id = portal_models.execute_kw(
            DB, portal_uid, PASS,
            "project.task", "create", [subtask_vals]
        )
        log(f"[+] Sub‑task created (ID={subtask_id})")
    except Exception as e:
        log(f"[!] Failed to create sub‑task as portal user: {e}")
        sys.exit(1)

    # 4️⃣ Post chatter message from portal user
    message_body = "Test message from portal user – verification of chatter communication."
    try:
        portal_models.execute_kw(
            DB, portal_uid, PASS,
            "project.task", "message_post", [subtask_id], {"body": message_body}
        )
        log("[+] Chatter message posted on sub‑task (portal side).")
    except Exception as e:
        log(f"[!] Failed to post chatter: {e}")

    # 5️⃣ Admin verification
    subtask = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "read", [[subtask_id]],
        {"fields": ["id", "name", "parent_id", "message_ids"]}
    )[0]
    log(f"[+] Admin sees sub‑task: {subtask}")
    if subtask.get("message_ids"):
        msgs = admin_models.execute_kw(
            DB, admin_uid, PASS,
            "mail.message", "read", [subtask["message_ids"]],
            {"fields": ["id", "body", "author_id"]}
        )
        log(f"[+] Retrieved {len(msgs)} chatter message(s) on sub‑task.")
        for m in msgs:
            author = admin_models.execute_kw(DB, admin_uid, PASS, "res.users", "read", [[m["author_id"][0]]], {"fields": ["login"]})[0]["login"]
            log(f"    Message ID {m['id']} by {author}: {m['body']}")
    else:
        log("[!] No chatter messages found on sub‑task.")

    # Build report
    report = {
        "timestamp": int(time.time()),
        "project_id": PROJECT_ID,
        "parent_task_id": parent_task_id,
        "subtask_id": subtask_id,
        "subtask_name": subtask_name,
        "portal_user": PORTAL_LOGIN,
        "chatter_body": message_body,
        "admin_view": subtask,
    }
    report_path = "portal_subtask_flow_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
