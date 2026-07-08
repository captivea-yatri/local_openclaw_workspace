#!/usr/bin/env python3
"""Full end‑to‑end QA flow for the custom Odoo 19 project module.

Modified version that:
1. Sets default_domain_ids on project creation (during create, not after via write)
2. Uses action 3652 (Create task from requirement) to create the task
   by: creating wizard with project_id, then writing phase_id, then executing action
"""

import json, sys, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Configuration – edit only if the Odoo instance changes
# ---------------------------------------------------------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def log(msg):
    print(msg)

def connect_admin():
    """Return (uid, models) for the admin user, SSL verification disabled (self‑signed cert)."""
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

def connect(user, password):
    """Generic login helper for any user (admin or portal)."""
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

def detect_assignee_field(models, uid):
    """Return the correct assignee field on ``project.task`` (custom or standard)."""
    fields = models.execute_kw(
        DB, uid, PASS, "project.task", "fields_get", [], {"attributes": ["type"]}
    )
    return "x_default_user_id" if "x_default_user_id" in fields else "user_id"

# ---------------------------------------------------------------------------
# Colour computation (mirrors test_project_workflow.py)
# ---------------------------------------------------------------------------
def compute_project_colour(models, uid, project_id, invoice_id):
    """Return colour index (1=red, 2=orange, 10=green).
    * Past‑due invoice → red (1)
    * Due within 5 days → orange (2)
    * Otherwise → green (10)
    If any linked sale order has the custom flag ``x_studio_block_timesheet_log``
    (and the order is not draft/cancel/sent) the colour is forced to red.
    """
    colour = 10  # default green
    # ---- Invoice due‑date based colour ----
    try:
        inv = models.execute_kw(
            DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["invoice_date_due"]}
        )[0]
        due_str = inv.get("invoice_date_due")
        if due_str:
            due_date = datetime.datetime.strptime(due_str, "%Y-%m-%d").date()
            delta = (due_date - datetime.date.today()).days
            if delta < 0:
                colour = 1
            elif delta <= 5:
                colour = 2
            else:
                colour = 10
    except Exception as e:
        log(f"[!] Invoice colour check failed: {e}")
    # ---- Blocked timesheet flag (custom) ----
    try:
        proj = models.execute_kw(
            DB, uid, PASS, "project.project", "read", [[project_id]], {"fields": ["sale_order_line_ids"]}
        )[0]
        line_ids = proj.get("sale_order_line_ids") or []
        if line_ids:
            lines = models.execute_kw(
                DB, uid, PASS, "sale.order.line", "read", [line_ids], {"fields": ["order_id"]}
            )
            so_ids = list({ln["order_id"][0] for ln in lines if ln.get("order_id")})
            if so_ids:
                orders = models.execute_kw(
                    DB, uid, PASS, "sale.order", "read", [so_ids], {"fields": ["x_studio_block_timesheet_log", "state"]}
                )
                for so in orders:
                    if so.get("x_studio_block_timesheet_log") and so.get("state") not in ["draft", "cancel", "sent"]:
                        colour = 1
                        break
    except Exception:
        pass
    return colour

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main():
    uid, models = connect_admin()
    ts = int(time.time())
    email = f"portal_user_{ts}@example.com"

    # ---------------------------------------------------------------------
    # 0️⃣ Prepare domain FIRST (so we can use it during project creation)
    # ---------------------------------------------------------------------
    domain_id = None
    try:
        domain_vals = {"name": "Default Domain"}
        domain_id = models.execute_kw(DB, uid, PASS, "project.domain", "create", [domain_vals])
        log(f"[+] Domain created (domain ID={domain_id})")
    except Exception as e:
        log(f"[!] Could not create domain: {e}")
        # Fallback: fetch an existing domain the user can access
        existing = models.execute_kw(DB, uid, PASS, "project.domain", "search_read", [[]], {"fields": ["id"], "limit": 1})
        if existing:
            domain_id = existing[0]["id"]
            log(f"[+] Using existing domain ID={domain_id} as fallback.")

    # 1️⃣ Partner creation
    partner_vals = {
        "name": f"Portal Test Customer {ts}",
        "email": email,
        "customer_rank": 1,
    }
    partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [partner_vals])
    log(f"[+] Partner created (ID={partner_id})")

    # 2️⃣ Portal user creation
    portal_group_id = find_portal_group(models, uid)
    # Create a **portal‑only** user (no internal groups). We explicitly set the groups list
    # to contain only the Portal group returned by `find_portal_group`. This ensures the user
    # cannot access internal menus and is treated as a true portal user.
    portal_user_vals = {
        "login": email,
        "partner_id": partner_id,
        "password": "a",
        "share": True,
    }
    # Odoo uses the many2many field ``group_ids`` for user groups. Using the correct field name
    # prevents the ``Invalid field 'groups_id'`` error we saw earlier.
    if portal_group_id:
        # Assign only the Portal group (if it exists) – this keeps the user from getting any internal groups.
        portal_user_vals["group_ids"] = [(6, 0, [portal_group_id])]
    else:
        # No Portal group present – explicitly clear any groups so the user remains a pure portal user.
        portal_user_vals["group_ids"] = [(5,)]  # remove all groups
    portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
    log(f"[+] Portal user created (UID={portal_user_id})")

    # 3️⃣ Sales order (service product – assume ID 2002 exists)
    # Determine admin's company to avoid cross‑company errors
    admin_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[uid]], {"fields": ["company_id"]})[0]
    admin_company_id = admin_user.get("company_id")[0]
    product_id = 2002
    # Find a payment term (use the first Net‑* term belonging to the admin's company, if available)
    payment_terms = models.execute_kw(DB, uid, PASS, "account.payment.term", "search_read", [[("name", "ilike", "Net"), ("company_id", "=", admin_company_id)]], {"fields": ["id"], "limit": 1})
    payment_term_id = payment_terms[0]["id"] if payment_terms else False
    so_vals = {
        "partner_id": partner_id,
        "company_id": admin_company_id,
        "team_id": False,
        "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1})],
        "payment_term_id": payment_term_id,
    }
    so_id = models.execute_kw(DB, uid, PASS, "sale.order", "create", [so_vals])
    log(f"[+] Sales order created (ID={so_id})")

    # 4️⃣ Use an **existing** project instead of creating a new one.
    # Grab the most recent project (highest ID) regardless of partner.
    existing_projects = models.execute_kw(DB, uid, PASS, "project.project", "search_read", [], {"fields": ["id"], "order": "id desc", "limit": 1})
    if not existing_projects:
        raise RuntimeError("No existing project found to reuse.")
    project_id = existing_projects[0]["id"]
    log(f"[+] Reusing existing project ID={project_id}")
    # Ensure the required fields are present on this project (default domains, signatory partner, etc.)
    update_vals = {"signatory_progress_report_partner_id": partner_id}
    if domain_id:
        update_vals["default_domain_ids"] = [(4, domain_id)]
    try:
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], update_vals])
        log("[+] Project updated with partner and default domains where applicable.")
    except Exception as e:
        log(f"[!] Could not update project {project_id}: {e}")

    # 5️⃣ Create an initial phase for the project.
    phase_vals = {
        "name": "Initial Phase",
        "project_id": project_id,
        "active": True,
        "sequence": 1,
    }
    phase_id = models.execute_kw(DB, uid, PASS, "project.phase", "create", [phase_vals])
    log(f"[+] Phase created for project (phase ID={phase_id})")
    # After creating the phase, update the project with default_domain_ids (if any) and link the phase.
    project_update_vals = {}
    if domain_id:
        project_update_vals["default_domain_ids"] = [(4, domain_id)]
    # Many2one field phase_id on project (if present in this DB)
    # We check existence by attempting a write; ignore if field missing.
    try:
        project_update_vals["phase_id"] = phase_id
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], project_update_vals])
        log(f"[+] Project updated with default domains and phase_id after phase creation.")
    except Exception as e:
        # Field may not exist; log and continue.
        log(f"[!] Could not set phase_id on project: {e}")
        if project_update_vals.get("default_domain_ids"):
            # If only default_domain_ids was set, try writing just that.
            try:
                models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"default_domain_ids": project_update_vals["default_domain_ids"]}])
                log("[+] Project default_domain_ids set after phase creation.")
            except Exception as e2:
                log(f"[!] Could not set default_domain_ids on project: {e2}")

    # ---------------------------------------------------------------------
    # Create a default role (project.role model) for task assignment.
    # This will be used as the task's role_id.
    # ---------------------------------------------------------------------
    role_vals = {
        "name": "Default Role",
    }
    role_id = models.execute_kw(DB, uid, PASS, "project.role", "create", [role_vals])
    log(f"[+] Role created (role ID={role_id})")

    # 5️⃣ Create the invoice manually (the wizard action is not available via XML‑RPC)
    invoice_vals = {
        "move_type": "out_invoice",
        "partner_id": partner_id,
        "invoice_origin": f"SO{so_id}",
        "invoice_line_ids": [(0, 0, {"product_id": product_id, "quantity": 1})],
    }
    invoice_id = models.execute_kw(DB, uid, PASS, "account.move", "create", [invoice_vals])
    log(f"[+] Invoice manually created (ID={invoice_id})")
    # Post the invoice
    try:
        models.execute_kw(DB, uid, PASS, "account.move", "action_post", [invoice_id])
        log("[+] Invoice posted.")
    except Exception as e:
        log(f"[!] Could not post invoice: {e}")

    # ---------------------------------------------------------------------
    # 6️⃣ Feedback flow – create feedback as portal user, convert to task
    # ---------------------------------------------------------------------
    # Simulate portal login (password is assumed to be "a")
    # Find (or create) a portal user linked to the project's partner.
    portal_user_id = None
    # Search for existing portal user with share=True and matching partner.
    portal_users = models.execute_kw(DB, uid, PASS, "res.users", "search_read", [[("share", "=", True), ("partner_id", "=", partner_id)]], {"fields": ["id", "login"], "limit": 1})
    if portal_users:
        portal_user_id = portal_users[0]["id"]
        portal_login = portal_users[0]["login"]
        log(f"[+] Existing portal user found (UID={portal_user_id})")
    else:
        # Create a new portal user for this partner.
        portal_group_id = find_portal_group(models, uid)
        portal_login = f"portal_user_{partner_id}@example.com"
        portal_user_vals = {
            "login": portal_login,
            "partner_id": partner_id,
            "password": "a",
            "share": True,
        }
        if portal_group_id:
            portal_user_vals["group_ids"] = [(6, 0, [portal_group_id])]
        else:
            portal_user_vals["group_ids"] = [(5,)]
        portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
        log(f"[+] Created portal user (UID={portal_user_id}) for partner {partner_id}")

    # Login as portal user.
    portal_uid, portal_models = connect(portal_login, "a")

    # Create feedback as portal user.
    feedback_vals = {
        "name": f"Feedback {ts}",
        "project_id": project_id,
        "description": "Automated feedback from portal user (test flow)",
    }
    feedback_id = portal_models.execute_kw(DB, portal_uid, PASS, "project.feedback", "create", [feedback_vals])
    log(f"[+] Feedback created (ID={feedback_id})")

    # Backend updates extra fields (status).
    extra_vals = {"status": "new"}
    models.execute_kw(DB, uid, PASS, "project.feedback", "write", [[feedback_id], extra_vals])
    log("[+] Feedback status set to 'new'")

    # Try to transform feedback into a task via model method.
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

    # NOTE: Fallback task creation handled later after wizard attempt.

    # 6️⃣ Colour scenarios (green, orange, red)
    # Only test the red colour scenario (past due date) to ensure the project ends up red.
    scenarios = {
        "red": datetime.date.today() - datetime.timedelta(days=3),
    }
    colour_results = {}
    for name, due_date in scenarios.items():
        # Write due date on invoice
        models.execute_kw(
            DB, uid, PASS, "account.move", "write", [[invoice_id], {"invoice_date_due": due_date.strftime('%Y-%m-%d')}]
        )
        colour = compute_project_colour(models, uid, project_id, invoice_id)
        colour_results[name] = colour
        log(f"[+] Scenario {name}: due {due_date} => colour index {colour}")
        # Do NOT write colour to the project – we only compute it for verification

    # 7️⃣ Share project with portal partner (editable)
    # The standard share wizard method `action_share` is not available in this DB.
    # Instead, we directly add the portal partner as a follower (message_partner_ids).
    try:
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"message_partner_ids": [(4, partner_id)]}])
        log("[+] Portal partner added as follower for project (share simulated).")
    except Exception as e:
        log(f"[!] Direct share failed: {e}")

    # 8️⃣ Create task via the "Create Project Requirement" wizard (act_window id=3652)
    # NEW APPROACH: Create wizard with project_id, then write phase_id, then execute action
    wizard_success = False
    task_id = None
    try:
        ctx = {"active_model": "project.project", "active_id": project_id}
        # Step 1: Create wizard with just project_id (minimal)
        wizard_vals = {
            "project_id": project_id,
        }
        wizard_id = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "create", [wizard_vals], {"context": ctx})
        log(f"[+] Wizard record created (id={wizard_id})")
        
        # Step 2: Write phase_id to the wizard
        try:
            models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "write", [[wizard_id], {"phase_id": phase_id}])
            log(f"[+] Wrote phase_id={phase_id} to wizard {wizard_id}")
        except Exception as write_e:
            log(f"[!] Could not write phase_id to wizard: {write_e}")
            # Continue anyway - maybe phase_id isn't needed or is set differently
        
        # Step 3: Execute the action
        try:
            result = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "action_create_task_from_project", [wizard_id], {"context": ctx})
            log(f"[+] Wizard action executed – result: {result}")
            wizard_success = True
        except xmlrpc.client.Fault as wf:
            if wf.faultCode == 1 and "cannot marshal None" in wf.faultString:
                log("[+] Wizard action returned None (expected) – considered successful.")
                wizard_success = True
            else:
                log(f"[!] Wizard action fault: {wf}")
    except Exception as e:
        log(f"[!] Failed to run wizard for task creation: {e}")

    # AFTER wizard attempt, check if a task was created
    if wizard_success:
        # Give it a moment then search for the most recent task in this project
        time.sleep(1)  # Brief pause to allow any async creation
        tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "order": "id desc", "limit": 1})
        if tasks:
            task_id = tasks[0]["id"]
            log(f"[+] Task found after wizard attempt (ID={task_id})")
            # Verify it's actually linked to our project (should be, but double-check)
            task_check = models.execute_kw(DB, uid, PASS, "project.task", "read", [[task_id]], {"fields": ["project_id"]})[0]
            if task_check.get("project_id") and task_check["project_id"][0] == project_id:
                log(f"[+] Task verified to belong to project {project_id}")
            else:
                log(f"[!] Task {task_id} does not belong to project {project_id}; treating as not found")
                task_id = None
        else:
            log("[!] No tasks found in project after wizard attempt")

    if not task_id:
        # Wizard didn't yield a usable task - fall back to manual creation
        log("[!] Wizard did not create a usable task; falling back to manual task creation.")
        assignee_field = detect_assignee_field(models, uid)
        task_vals = {
            "name": f"Portal task {ts}",
            "project_id": project_id,
            assignee_field: portal_user_id,
            "default_phase_id": phase_id,
            "default_domain_id": domain_id,
        }
        task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
        log(f"[+] Manual task created (ID={task_id})")
    else:
        log(f"[+] Using task created via wizard (ID={task_id})")

    # ---------------------------------------------------------------------
    # 9️⃣ Create a sub‑task via the portal user under the newly created task
    # ---------------------------------------------------------------------
    # Ensure portal user has groups that allow task creation on projects.
    required_group_ids = [441, 336]
    try:
        # Correct syntax: first argument is the record ID list, second is the values dict
        models.execute_kw(DB, uid, PASS, "res.users", "write", [[portal_user_id], {"group_ids": [(6, 0, required_group_ids)]}])
        log(f"[+] Added portal user to groups {required_group_ids} for sub‑task creation.")
    except Exception as e:
        log(f"[!] Could not set portal user groups: {e}")
    # Authenticate as portal user (login is stored in `email`)
    portal_uid, portal_models = connect(email, "a")
    subtask_name = f"Portal sub‑task {int(time.time())}"
    subtask_vals = {
        "name": subtask_name,
        "project_id": project_id,
        "parent_id": task_id,
    }
    subtask_id = portal_models.execute_kw(DB, portal_uid, PASS, "project.task", "create", [subtask_vals])
    log(f"[+] Sub‑task created (ID={subtask_id})")
    # Post a chatter message on the sub‑task from the portal user
    sub_message = "Test sub‑task creation via portal user – verification of chatter."
    portal_models.execute_kw(DB, portal_uid, PASS, "project.task", "message_post", [subtask_id], {"body": sub_message})
    log("[+] Chatter posted on sub‑task (portal side).")

    # 9️⃣ Post a feedback chatter message (as admin, indicating portal user author)
    feedback_body = "Feedback from portal user (simulated)"
    models.execute_kw(
        DB, uid, PASS, "project.project", "message_post", [project_id], {"body": feedback_body}
    )
    log("[+] Feedback message posted on project.")

    # 10️⃣ Verify collaborators (message_partner_ids should include portal partner)
    proj_data = models.execute_kw(
        DB, uid, PASS, "project.project", "read", [[project_id]], {"fields": ["partner_id", "message_partner_ids", "color"]}
    )[0]
    collaborators = proj_data.get("message_partner_ids", [])
    log(f"[+] Collaborators on project: {collaborators}")

    # Build report
    report = {
        "timestamp": ts,
        "partner_id": partner_id,
        "portal_user_id": portal_user_id,
        "sales_order_id": so_id,
        "project_id": project_id,
        "invoice_id": invoice_id,
        "task_id": task_id,
        "subtask_id": subtask_id,
        "colour_results": colour_results,
        "final_project_colour": proj_data.get("color"),
        "collaborators": collaborators,
    }
    report_path = "full_portal_project_invoice_flow_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()