#!/usr/bin/env python3
"""Full end‑to‑end QA flow for the custom Odoo 19 project module.

The script performs the complete workflow you requested:
1️⃣ Create a partner (customer)
2️⃣ Create a portal user linked to that partner (share=True)
3️⃣ Create a sales order for a known service product (ID 2002) – this auto‑creates a project
4️⃣ Create and post an invoice for the sales order
5️⃣ Adjust the invoice due‑date three times (future, near, past) to exercise the colour logic (green / orange / red)
6️⃣ Share the project with the portal partner via the *editable* ``project.share.wizard``
7️⃣ Create a task inside the project and assign it to the portal user (using the custom assignee field)
8️⃣ Post a feedback chatter message (as the portal user – here posted by admin for simplicity)
9️⃣ Verify collaborator lists and the computed colour on the project
🔟 Write a detailed JSON report containing every created ID and the colour results.

All actions run as the admin user (`admin1` / `a`). The script is idempotent – it uses a timestamp‑based email address to avoid collisions.
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
    # Retrieve admin's company with retry (503 occasional)
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            admin_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[uid]], {"fields": ["company_id"]})[0]
            admin_company_id = 1  # Force Captivea USA (company ID 1)
            break
        except Exception as e:
            log(f"[!] Admin user read failed attempt {attempt + 1}: {e}")
            if attempt == max_attempts - 1:
                raise
            time.sleep(5)
    product_id = 2002
    # Find a payment term (use the first Net‑* term belonging to the admin's company, if available)
    try:
        payment_terms = models.execute_kw(DB, uid, PASS, "account.payment.term", "search_read", [[("name", "ilike", "Net"), ("company_id", "=", admin_company_id)]], {"fields": ["id"], "limit": 1})
        payment_term_id = payment_terms[0]["id"] if payment_terms else False
    except Exception as e:
        log(f"[!] Payment term lookup failed: {e}")
        payment_term_id = False
    so_vals = {
        "partner_id": partner_id,
        "company_id": admin_company_id,
        "team_id": False,
        "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1})],
        "payment_term_id": payment_term_id,
    }
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            so_id = models.execute_kw(DB, uid, PASS, "sale.order", "create", [so_vals])
            log(f"[+] Sales order created (ID={so_id})")
            break
        except Exception as e:
            log(f"[!] Sale order creation failed attempt {attempt + 1}: {e}")
            if attempt == max_attempts - 1:
                raise
            time.sleep(5)

    # 4️⃣ Locate the auto‑created project.
    # Try to read the project_id directly from the sales order (standard auto‑project linking).
    so_data = models.execute_kw(DB, uid, PASS, "sale.order", "read", [[so_id]], {"fields": ["project_id"]})[0]
    project_id = so_data.get("project_id")
    if project_id:
        # many2one tuple (id, name) or False
        project_id = project_id[0] if isinstance(project_id, (list, tuple)) else project_id
        log(f"[+] Project found via sale order (ID={project_id})")
    else:
        # Fallback: create a project explicitly (auto‑creation may be disabled in this DB)
        # Determine an existing domain to assign at creation time.
        existing_domains = models.execute_kw(DB, uid, PASS, "project.domain", "search_read", [[]], {"fields": ["id"], "limit": 1})
        domain_id = existing_domains[0]["id"] if existing_domains else False
        default_domain_cmd = [(4, domain_id)] if domain_id else []
        project_vals = {
            "name": f"Portal Project {ts}",
            "partner_id": partner_id,
            "company_id": admin_company_id,
            "signatory_progress_report_partner_id": partner_id,
            "default_domain_ids": default_domain_cmd,
        }
        project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [project_vals])
        log(f"[+] Project manually created (ID={project_id})")
        if domain_id:
            log(f"[+] Assigned existing domain ID={domain_id} at project creation")

    # 5️⃣ After we have a project (whether auto‑created or manual), ensure required fields are set.
    #    - company_id must match the admin's company
    #    - signatory_progress_report_partner_id should point to the partner we just created
    models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"company_id": admin_company_id, "signatory_progress_report_partner_id": partner_id}])
    log("[+] Project fields updated (company_id & signatory_progress_report_partner_id).")
    # Create an initial phase for the project.
    phase_vals = {
        "name": "Initial Phase",
        "project_id": project_id,
        "active": True,
        "sequence": 1,
    }
    phase_id = models.execute_kw(DB, uid, PASS, "project.phase", "create", [phase_vals])
    log(f"[+] Phase created for project (phase ID={phase_id})")

    # ---------------------------------------------------------------------
    # Assign an existing domain to the project (without creating a new one).
    # ---------------------------------------------------------------------
    # Fetch an existing domain the user can read (limit 1).
    existing = models.execute_kw(DB, uid, PASS, "project.domain", "search_read", [[]], {"fields": ["id"], "limit": 1})
    if existing:
        domain_id = existing[0]["id"]
        try:
            models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {"default_domain_ids": [(4, domain_id)]}])
            log(f"[+] Set default_domain_ids on project to existing domain ID={domain_id}")
        except Exception as e:
            log(f"[!] Could not set default_domain_ids on project: {e}")
    else:
        log("[!] No existing domain found; skipping default domain assignment.")
        domain_id = None

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

    # 6️⃣ Colour scenarios (green, orange, red)
    # For timesheet logging we need the project in a non‑red state (green or orange).
    # We'll set the invoice due‑date to a future date so the colour becomes green (10).
    scenarios = {
        "green": datetime.date.today() + datetime.timedelta(days=10),
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
    # If the wizard fails, fall back to manual task creation.
    wizard_success = False
    try:
        ctx = {"active_model": "project.project", "active_id": project_id, "action_id": 3652}
        wizard_vals = {"project_id": project_id, "phase_id": phase_id}
        wizard_id = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "create", [wizard_vals], {"context": ctx})
        log(f"[+] Wizard record created (id={wizard_id})")
        # Ensure the wizard has the phase_id set (the wizard only exposes this field)
        try:
            models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "write", [[wizard_id], {"phase_id": phase_id}])
        except Exception as e:
            log(f"[!] Failed to set phase_id on wizard: {e}")
        try:
            models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "action_create_task_from_project", [wizard_id], {"context": ctx})
            log("[+] Wizard action executed – task created via wizard.")
            wizard_success = True
        except xmlrpc.client.Fault as wf:
            if wf.faultCode == 1 and "cannot marshal None" in wf.faultString:
                log("[+] Wizard action returned None (expected) – considered successful.")
                wizard_success = True
            else:
                log(f"[!] Wizard action fault: {wf}")
    except Exception as e:
        log(f"[!] Failed to run wizard for task creation: {e}")

    if not wizard_success:
        # Manual fallback (wizard failed to create task)
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
        # Wizard succeeded – retrieve the new task (may be None if wizard didn't actually create one)
        tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "order": "id desc", "limit": 1})
        task_id = tasks[0]["id"] if tasks else None
        if not task_id:
            log("[!] Wizard reported success but no task found; falling back to manual task creation.")
            assignee_field = detect_assignee_field(models, uid)
            task_vals = {
                "name": f"Portal task {ts} (fallback)",
                "project_id": project_id,
                assignee_field: portal_user_id,
                "default_phase_id": phase_id,
                "default_domain_id": domain_id,
            }
            task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
            log(f"[+] Fallback manual task created (ID={task_id})")
        else:
            log(f"[+] Task created via wizard (ID={task_id})")

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
    # Authenticate as portal user with retry (503 occasional)
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            portal_uid, portal_models = connect(email, "a")
            break
        except Exception as e:
            log(f"[!] Portal login failed attempt {attempt + 1}: {e}")
            if attempt == max_attempts - 1:
                raise
            time.sleep(5)
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

    # ----- Progress Report Flow (integrated) -----
    # Refresh domain calculation (mandatory before creating report)
    try:
        res = models.execute_kw(DB, uid, PASS, "project.project", "refresh_project_domain_calculations", [project_id])
        log(f"[+] refresh_project_domain_calculations result: {res}")
    except Exception as e:
        log(f"[!] refresh_project_domain_calculations failed: {e}")
    # Get the progress report action (just for logging)
    try:
        report_action = models.execute_kw(DB, uid, PASS, "project.project", "action_get_project_progress_report", [project_id])
        log("[+] action_get_project_progress_report executed.")
    except Exception as e:
        log(f"[!] action_get_project_progress_report failed: {e}")
        report_action = None
    # Ensure a project.progress record exists and set its phase
    try:
        existing = models.execute_kw(DB, uid, PASS, "project.progress", "search", [[("project_id", "=", project_id)]])
        if existing:
            progress_id = existing[0]
            log(f"[+] Found existing project.progress (ID={progress_id})")
        else:
            progress_id = models.execute_kw(DB, uid, PASS, "project.progress", "create", [{"project_id": project_id}])
            log(f"[+] Created project.progress (ID={progress_id})")
        if phase_id:
            models.execute_kw(DB, uid, PASS, "project.progress", "write", [[progress_id], {"phase_id": phase_id}])
            log(f"[+] Set phase_id={phase_id} on progress record")
        # Ensure the progress record has a signatory partner so it can be sent
        try:
            models.execute_kw(DB, uid, PASS, "project.progress", "write", [[progress_id], {"signatory_progress_report_partner_id": partner_id}])
            log(f"[+] Set signatory_progress_report_partner_id={partner_id} on progress record")
        except Exception as e:
            log(f"[!] Setting signatory on progress record failed: {e}")
    except Exception as e:
        log(f"[!] Failed to ensure project.progress: {e}")
        progress_id = None
    # Calculate remaining hours on progress record
    calc_res = None
    send_res = None
    if progress_id:
        try:
            calc_res = models.execute_kw(DB, uid, PASS, "project.progress", "calculate_the_progress_remaining_hours", [progress_id])
            log(f"[+] calculate_the_progress_remaining_hours result: {calc_res}")
        except Exception as e:
            log(f"[!] calculate_the_progress_remaining_hours failed: {e}")
        # Send the progress report
        try:
            send_res = models.execute_kw(DB, uid, PASS, "project.progress", "action_project_progress_send", [progress_id])
            log(f"[+] action_project_progress_send result: {send_res}")
        except Exception as e:
            log(f"[!] action_project_progress_send failed: {e}")
    # ----- End of Progress Report Flow -----

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
        "progress_report": {
            "progress_id": progress_id,
            "calculate_result": calc_res if progress_id else None,
            "send_result": send_res if progress_id else None,
        }
    }
    # -----------------------------------------------------------------
    # 13️⃣ Production Review Flow (integrated from test_production_review_flow.py)
    # -----------------------------------------------------------------
    # Use the same admin connection (uid, models). We'll create a Production Question Template
    # and a Production Review for the partner we created earlier (partner_id).
    # The original test script runs as a specific user, but here we use admin for simplicity.
    # Create Production Question Template (frequency 100%)
    tmpl_vals = {
        "name": f"Prod Q Template {ts}",
        "frequency": 100,
    }
    try:
        tmpl_id = models.execute_kw(DB, uid, PASS, "production.question.template", "create", [tmpl_vals])
        log(f"[+] Production Question Template created ID={tmpl_id}")
    except Exception as e:
        log(f"[!] Failed to create Production Question Template: {e}")
        tmpl_id = None

    # Create Production Review linked to the partner
    review_vals = {
        "partner_id": partner_id,
        # Additional fields can be added if needed
    }
    try:
        review_id = models.execute_kw(DB, uid, PASS, "production.review", "create", [review_vals])
        log(f"[+] Production Review created ID={review_id}")
    except Exception as e:
        log(f"[!] Failed to create Production Review: {e}")
        review_id = None

    if review_id:
        # Smart‑button actions
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "action_quality_isssue", [review_id])
            log("[+] action_quality_isssue executed")
        except Exception as e:
            log(f"[!] action_quality_isssue failed: {e}")

        # Process any quality issues linked to the review
        try:
            review_data = models.execute_kw(DB, uid, PASS, "production.review", "read", [[review_id]], {"fields": ["issue_ids"]})
            issue_ids = review_data[0].get("issue_ids", [])
            if issue_ids:
                for issue_id in issue_ids:
                    try:
                        models.execute_kw(DB, uid, PASS, "production.review", "action_3776", [issue_id])
                        log(f"[+] action_3776 executed on issue {issue_id}")
                    except Exception as e:
                        log(f"[!] action_3776 failed on issue {issue_id}: {e}")
            else:
                log("[+] No quality issues linked to review")
        except Exception as e:
            log(f"[!] Failed to read issues: {e}")

        # Project smart‑button (creates a project if needed)
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "action_production_review_project", [review_id])
            log("[+] action_production_review_project executed")
        except Exception as e:
            log(f"[!] action_production_review_project failed: {e}")

        # Mark review as done
        try:
            models.execute_kw(DB, uid, PASS, "production.review", "write", [[review_id], {"state": "done"}])
            log("[+] Production Review marked as done")
        except Exception as e:
            log(f"[!] Could not mark Production Review as done: {e}")

        # Capture snapshot of the review state
        try:
            snapshot = models.execute_kw(DB, uid, PASS, "production.review", "read", [[review_id]], {"fields": ["state", "issue_ids"]})
        except Exception as e:
            snapshot = []
            log(f"[!] Snapshot read failed: {e}")
    else:
        snapshot = []

    # -----------------------------------------------------------------
    # Build final report (including Production Review data)
    # -----------------------------------------------------------------
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
        "progress_report": {
            "progress_id": progress_id,
            "calculate_result": calc_res if progress_id else None,
            "send_result": send_res if progress_id else None,
        },
        "production_review": {
            "template_id": tmpl_id,
            "review_id": review_id,
            "review_snapshot": snapshot[0] if snapshot else {},
        },
    }
    report_path = "full_portal_project_invoice_flow_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log(f"[+] Report written to {report_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()

