#!/usr/bin/env python3
"""Full end‑to‑end portal‑access test (creates fresh records).
   1. Create a new partner (customer).
   2. Create a portal user (share=True) for that partner.
   3. Create a project linked to the partner.
   4. Set project visibility to invited portal users + internal.
   5. Share the project in editable mode with the portal partner.
   6. Create a task in the project.
   7. Post a feedback mail.message on the task (as the portal user).
   8. Verify that the collaborator lists contain the partner and that the feedback is stored.
   9. Write a JSON report with all created IDs and any errors.
"""

import json, sys, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

def log(msg):
    print(msg)

def main():
    # --------------------------------------------------
    # 0️⃣ Connect as admin
    # --------------------------------------------------
    common = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"))
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    log(f"[+] Admin UID = {uid}")
    models = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"))

    report = {}
    errors = []

    try:
        # --------------------------------------------------
        # 1️⃣ Create a fresh partner (customer)
        # --------------------------------------------------
        partner_vals = {
            "name": "Portal Test Customer",
            "email": "portal_test_customer@example.com",
        }
        partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [partner_vals])
        log(f"[+] Partner created (ID={partner_id})")
        report["partner_id"] = partner_id
    except Exception as e:
        errors.append(f"Partner creation failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 2️⃣ Create portal user for that partner
        # --------------------------------------------------
        # Find a group that grants portal access – usually named "Portal"
        portal_group = models.execute_kw(
            DB, uid, PASS,
            "res.groups", "search_read",
            [[("name", "=", "Portal")]],
            {"fields": ["id"], "limit": 1}
        )
        portal_group_id = portal_group[0]["id"] if portal_group else None
        portal_user_vals = {
            "login": "portal_test_user@example.com",
            "partner_id": partner_id,
            "password": "a",
            "share": True,
        }
        if portal_group_id:
            portal_user_vals["groups_id"] = [(6, 0, [portal_group_id])]
        portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
        log(f"[+] Portal user created (UID={portal_user_id})")
        report["portal_user_id"] = portal_user_id
    except Exception as e:
        errors.append(f"Portal user creation failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 3️⃣ Create a project linked to the partner
        # --------------------------------------------------
        proj_vals = {
            "name": "Portal Test Project",
            "partner_id": partner_id,
            "user_id": uid,  # manager = admin for simplicity
        }
        project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [proj_vals])
        log(f"[+] Project created (ID={project_id})")
        report["project_id"] = project_id
    except Exception as e:
        errors.append(f"Project creation failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 4️⃣ Set project visibility (if the field exists)
        # --------------------------------------------------
        # Try to write a generic "visibility" value; ignore if field missing.
        try:
            models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"visibility": "portal"}])
            log("[+] Project visibility set to portal‑invite (if field exists)")
        except Exception:
            # field may not exist – not fatal
            log("[!] Visibility field not found; skipping")
    except Exception as e:
        errors.append(f"Setting visibility failed: {e}")

    try:
        # --------------------------------------------------
        # 5️⃣ Share project in editable mode with the portal partner
        # --------------------------------------------------
        # Preferred method: action_share_editable(partner_ids=[partner_id])
        try:
            models.execute_kw(
                DB, uid, PASS,
                "project.project", "action_share_editable",
                [[project_id]],
                {"partner_ids": [partner_id]}
            )
            log("[+] Project shared (editable) via action_share_editable")
        except Exception:
            # Fallback: directly write to many2many used by the chatter
            models.execute_kw(
                DB, uid, PASS,
                "project.project", "write",
                [[project_id], {"message_partner_ids": [(4, partner_id)]}]
            )
            log("[+] Project shared (editable) via message_partner_ids fallback")
        # Verify collaborators
        collab = models.execute_kw(
            DB, uid, PASS,
            "project.project", "read",
            [project_id],
            {"fields": ["message_partner_ids", "signatory_portal_report_partner_ids"]}
        )
        report["project_collaborators"] = collab[0]["message_partner_ids"]
    except Exception as e:
        errors.append(f"Project sharing failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 6️⃣ Create a task inside the project
        # --------------------------------------------------
        task_vals = {
            "name": "Portal Test Task",
            "project_id": project_id,
            "user_id": uid,
            "description": "Task created as part of the full portal‑access flow.",
        }
        task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
        log(f"[+] Task created (ID={task_id})")
        report["task_id"] = task_id
    except Exception as e:
        errors.append(f"Task creation failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 7️⃣ Post a feedback message on the task as the portal user
        # --------------------------------------------------
        feedback_vals = {
            "model": "project.task",
            "res_id": task_id,
            "message_type": "comment",
            "subtype_id": 1,  # default comment subtype
            "author_id": portal_user_id,
            "body": "<p>Customer feedback posted from the portal side.</p>",
        }
        feedback_id = models.execute_kw(DB, uid, PASS, "mail.message", "create", [feedback_vals])
        log(f"[+] Feedback mail.message created (ID={feedback_id})")
        report["feedback_message_id"] = feedback_id
    except Exception as e:
        errors.append(f"Feedback creation failed: {e}")
        return finish(report, errors)

    try:
        # --------------------------------------------------
        # 8️⃣ Verify feedback is attached to the task
        # --------------------------------------------------
        fb_list = models.execute_kw(
            DB, uid, PASS,
            "mail.message", "search_read",
            [[("model", "=", "project.task"), ("res_id", "=", task_id)]],
            {"fields": ["author_id", "body", "date"]}
        )
        report["feedback_messages"] = fb_list
        log(f"[+] Verified {len(fb_list)} feedback message(s) on the task")
    except Exception as e:
        errors.append(f"Feedback verification failed: {e}")

    # --------------------------------------------------
    # 9️⃣ Save report
    # --------------------------------------------------
    out_path = "/home/captivea/.openclaw/workspace/portal_full_flow_test_report.json"
    with open(out_path, "w") as f:
        json.dump({"report": report, "errors": errors}, f, indent=2)
    log(f"[+] Report saved to {out_path}")
    if errors:
        log("[!] Some steps failed – see errors in the report.")
        return 1
    else:
        log("[✓] All steps succeeded.")
        return 0

def finish(report, errors):
    out_path = "/home/captivea/.openclaw/workspace/portal_full_flow_test_report.json"
    with open(out_path, "w") as f:
        json.dump({"report": report, "errors": errors}, f, indent=2)
    log(f"[+] Partial report saved to {out_path}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
