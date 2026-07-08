#!/usr/bin/env python3
"""Create a sub‑task in project 2904 as portal user and verify.
Steps:
1️⃣ Ensure portal user has groups that allow task creation.
2️⃣ Authenticate as portal user.
3️⃣ Create sub‑task under the latest existing task of the project.
4️⃣ Post a chatter message.
5️⃣ Verify as admin and output a JSON report.
"""

import ssl, xmlrpc.client, json, sys, time
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"
PORTAL_LOGIN = "portal_user_1780913589@example.com"
PORTAL_PASS = "a"
PROJECT_ID = 2904

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
    # ---------- Admin side ----------
    admin_uid, admin_models = connect(ADMIN, PASS)

    # Find latest task in the project (to be the parent)
    tasks = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "search_read",
        [[("project_id", "=", PROJECT_ID)]],
        {"fields": ["id", "name"], "order": "id desc", "limit": 1}
    )
    if not tasks:
        log("[!] No existing tasks in project – cannot create sub‑task.")
        sys.exit(1)
    parent_task_id = tasks[0]["id"]
    log(f"[+] Parent task found: {parent_task_id}")

    # Locate portal user record
    portal_user = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "res.users", "search_read",
        [[("login", "=", PORTAL_LOGIN)]],
        {"fields": ["id", "login", "group_ids"]}
    )
    if not portal_user:
        log("[!] Portal user not found.")
        sys.exit(1)
    portal_user = portal_user[0]
    log(f"[+] Portal user ID={portal_user['id']}")

    # Ensure portal user belongs to groups that allow creating tasks on projects
    # Known groups that grant such rights: "Can Create/Delete Project" (441) and "Project Dashboard User" (336)
    required_group_ids = [441, 336]
    admin_models.execute_kw(
        DB, admin_uid, PASS,
        "res.users", "write",
        [[portal_user['id'], {"group_ids": [(6, 0, required_group_ids)]}]]
    )
    log("[+] Updated portal user groups for project task rights.")

    # ---------- Portal side ----------
    portal_uid, portal_models = connect(PORTAL_LOGIN, PORTAL_PASS)
    log(f"[+] Authenticated as portal user (uid={portal_uid})")

    # Create sub‑task under the parent task
    subtask_name = f"Portal sub‑task {int(time.time())}"
    subtask_vals = {
        "name": subtask_name,
        "project_id": PROJECT_ID,
        "parent_id": parent_task_id,
    }
    subtask_id = portal_models.execute_kw(
        DB, portal_uid, PASS,
        "project.task", "create", [subtask_vals]
    )
    log(f"[+] Sub‑task created (ID={subtask_id})")

    # Post a chatter message from the portal user on the sub‑task
    message_body = "Test sub‑task creation via portal user – verification of chatter."
    portal_models.execute_kw(
        DB, portal_uid, PASS,
        "project.task", "message_post", [subtask_id], {"body": message_body}
    )
    log("[+] Chatter message posted on sub‑task (portal side).")

    # ---------- Admin verification ----------
    subtask = admin_models.execute_kw(
        DB, admin_uid, PASS,
        "project.task", "read", [[subtask_id]],
        {"fields": ["id", "name", "parent_id", "message_ids"]}
    )[0]
    log(f"[+] Admin sees sub‑task: {subtask}")
    messages = []
    if subtask.get("message_ids"):
        msgs = admin_models.execute_kw(
            DB, admin_uid, PASS,
            "mail.message", "read", [subtask["message_ids"]],
            {"fields": ["id", "body", "author_id"]}
        )
        for m in msgs:
            author = admin_models.execute_kw(DB, admin_uid, PASS, "res.users", "read", [[m["author_id"][0]]], {"fields": ["login"]})[0]["login"]
            messages.append({"id": m["id"], "body": m["body"], "author": author})
        log(f"[+] Retrieved {len(messages)} chatter message(s) on sub‑task.")
    else:
        log("[!] No chatter messages found on sub‑task.")

    # Build and write report
    report = {
        "timestamp": int(time.time()),
        "project_id": PROJECT_ID,
        "parent_task_id": parent_task_id,
        "subtask_id": subtask_id,
        "subtask_name": subtask_name,
        "portal_user": PORTAL_LOGIN,
        "chatter_body": message_body,
        "admin_view": subtask,
        "chatter_messages": messages,
    }
    report_path = "create_portal_subtask_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))
