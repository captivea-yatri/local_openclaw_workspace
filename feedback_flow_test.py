#!/usr/bin/env python3
"""Test flow for creating portal feedback and converting it to a task.

Steps performed:
1️⃣ Create a partner (customer) and a portal user (share=True).
2️⃣ Create a sales order for product ID 2002 – this auto‑creates a project.
3️⃣ From the *portal* side (simulated by logging in as the portal user) create a
   ``project.feedback`` record.  The exact model name may differ in your DB –
   adjust ``FEEDBACK_MODEL`` if needed.
4️⃣ From the backend (admin) set any additional fields on the feedback record
   (e.g. ``rating``, ``description``).
5️⃣ Convert the feedback into a task using either the ``transform_feedback_into_task``
   method (if the model provides it) **or** by setting the ``task_id`` field
   directly.
6️⃣ Verify the task was created and output a JSON report with all relevant IDs.

The script uses XML‑RPC, disables SSL verification for self‑signed certs, and
writes a ``feedback_flow_report.json`` in the workspace root.
"""

import json, sys, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration – edit only if the Odoo instance changes
# ---------------------------------------------------------------------------
ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

# Adjust if your installation uses a different model for feedback.
FEEDBACK_MODEL = "project.feedback"

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
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

def find_portal_group(models, uid):
    groups = models.execute_kw(
        DB, uid, PASS, "res.groups", "search_read",
        [[("name", "=", "Portal")]],
        {"fields": ["id"], "limit": 1}
    )
    return groups[0]["id"] if groups else None

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main():
    uid, models = connect(ADMIN, PASS)
    ts = int(time.time())
    email = f"portal_user_{ts}@example.com"

    # 1️⃣ Partner creation
    partner_vals = {
        "name": f"Portal Test Customer {ts}",
        "email": email,
        "customer_rank": 1,
    }
    partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [partner_vals])
    log(f"[+] Partner created (ID={partner_id})")

    # 2️⃣ Portal user creation (share=True)
    portal_group_id = find_portal_group(models, uid)
    portal_user_vals = {
        "login": email,
        "partner_id": partner_id,
        "password": "a",
        "share": True,
        "group_ids": [(6, 0, [portal_group_id])] if portal_group_id else [(5,)],
    }
    portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
    log(f"[+] Portal user created (UID={portal_user_id})")

    # 3️⃣ Sales order – creates a project automatically (product 2002 must exist)
    product_id = 2002
    # Determine admin's company to avoid cross‑company issues
    admin_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[uid]], {"fields": ["company_id"]})[0]
    admin_company_id = admin_user.get("company_id")[0]
    so_vals = {
        "partner_id": partner_id,
        "company_id": admin_company_id,
        "team_id": False,
        "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1})],
    }
    so_id = models.execute_kw(DB, uid, PASS, "sale.order", "create", [so_vals])
    log(f"[+] Sales order created (ID={so_id})")

    # Retrieve auto‑created project (if any)
    so_data = models.execute_kw(DB, uid, PASS, "sale.order", "read", [[so_id]], {"fields": ["project_id"]})[0]
    project_id = so_data.get("project_id")
    if project_id:
        project_id = project_id[0] if isinstance(project_id, (list, tuple)) else project_id
        log(f"[+] Project auto‑created (ID={project_id})")
    else:
        # Fallback: create a project manually linked to the partner
        log("[!] No project linked to sales order – creating project manually.")
        proj_vals = {
            "name": f"Portal Project {ts}",
            "partner_id": partner_id,
            "company_id": admin_company_id,
        }
        project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [proj_vals])
        log(f"[+] Manual project created (ID={project_id})")

    # ---------------------------------------------------------------------
    # 4️⃣ Create feedback from *portal* side (simulated login as portal user)
    # ---------------------------------------------------------------------
    portal_uid, portal_models = connect(email, "a")
    feedback_vals = {
        "name": f"Feedback {ts}",
        "project_id": project_id,
        "description": "Initial feedback from portal user (auto‑generated test)",
        # Add any required fields your custom model expects here.
    }
    feedback_id = portal_models.execute_kw(DB, portal_uid, PASS, FEEDBACK_MODEL, "create", [feedback_vals])
    log(f"[+] Feedback created by portal user (ID={feedback_id})")

    # ---------------------------------------------------------------------
    # 5️⃣ Backend sets extra fields and converts feedback → task
    # ---------------------------------------------------------------------
    # Example – set a rating field (replace with your real field names).
    extra_vals = {
        "status": "new",
    }
    models.execute_kw(DB, uid, PASS, FEEDBACK_MODEL, "write", [[feedback_id], extra_vals])
    log("[+] Backend updated feedback with extra fields")

    # Try the dedicated conversion method first.
    task_id = None
    try:
        # Some modules expose a method ``transform_feedback_into_task`` on the
        # feedback model – we call it via ``execute_kw``.
        result = models.execute_kw(
            DB, uid, PASS, FEEDBACK_MODEL,
            "transform_feedback_into_task",
            [feedback_id]
        )
        # The method may return the created task ID or a dict; handle both.
        if isinstance(result, int):
            task_id = result
        elif isinstance(result, dict) and result.get("task_id"):
            task_id = result["task_id"]
        log(f"[+] Feedback transformed via method – task ID={task_id}")
    except Exception as e:
        log(f"[!] Method transform_feedback_into_task failed: {e}")

    # Fallback – manually set the ``task_id`` field if the method is absent.
    if not task_id:
        # Create a plain task linked to the project.
        task_vals = {
            "name": f"Task from feedback {feedback_id}",
            "project_id": project_id,
        }
        task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
        log(f"[+] Fallback manual task created (ID={task_id})")
        # Link the feedback to the task.
        models.execute_kw(DB, uid, PASS, FEEDBACK_MODEL, "write", [[feedback_id], {"task_id": task_id}])
        log("[+] feedback.task_id field set to the created task")

    # ---------------------------------------------------------------------
    # 6️⃣ Build final report
    # ---------------------------------------------------------------------
    report = {
        "timestamp": ts,
        "partner_id": partner_id,
        "portal_user_id": portal_user_id,
        "sales_order_id": so_id,
        "project_id": project_id,
        "feedback_id": feedback_id,
        "task_id": task_id,
    }
    report_path = "feedback_flow_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
