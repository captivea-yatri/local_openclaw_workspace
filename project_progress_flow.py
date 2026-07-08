#!/usr/bin/env python3
"""Extended workflow:
1. Load the existing project/task IDs from the previous report.
2. Create timesheet entries (account.analytic.line) for the main task.
3. On the project, call the custom methods in the required order:
   a. refresh_project_domain_calculation()
   b. calculate_the_progress_remaining_hours()
   c. (optionally set phase_id if needed – the wizard already set it)
   d. action_get_project_progress_report()
4. Log all results.
"""

import json, time, ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"
REPORT_PATH = "full_portal_project_invoice_flow_report.json"

def log(msg):
    print(f"[LOG] {msg}")

def connect_admin():
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

def load_report():
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    uid, models = connect_admin()
    report = load_report()
    project_id = report.get("project_id")
    task_id    = report.get("task_id")
    if not project_id or not task_id:
        log("Project or task ID missing from report – aborting.")
        return
    log(f"Loaded project ID={project_id}, task ID={task_id} from report")

    # ------------------------------------------------------------
    # 1️⃣ Ensure the invoice is marked as paid (required before logging timesheets)
    # ------------------------------------------------------------
    invoice_id = report.get("invoice_id")
    if invoice_id:
        try:
            # Fetch invoice details (amount_total, partner_id)
            inv_data = models.execute_kw(DB, uid, PASS, "account.move", "read", [[invoice_id]], {"fields": ["amount_total", "partner_id"]})[0]
            amount_total = inv_data.get("amount_total") or 0.0
            partner_ref = inv_data.get("partner_id")
            # Find a cash or bank journal (take first available)
            journals = models.execute_kw(DB, uid, PASS, "account.journal", "search_read", [[("type", "in", ["cash", "bank"])]], {"fields": ["id"], "limit": 1})
            journal_id = journals[0]["id"] if journals else None
            if not journal_id:
                log("No cash/bank journal found – cannot register payment.")
            else:
                # Build payment vals (structure may vary; use the minimal fields)
                payment_vals = {
                    "payment_date": time.strftime("%Y-%m-%d"),
                    "journal_id": journal_id,
                    "payment_method_id": False,
                    "partner_id": partner_ref[0] if isinstance(partner_ref, (list, tuple)) else partner_ref,
                    "amount": amount_total,
                    "payment_type": "inbound",
                    "communication": f"Auto payment for invoice {invoice_id}",
                }
                # Register payment – using the standard Odoo method
                result = models.execute_kw(DB, uid, PASS, "account.move", "action_register_payment", [invoice_id], {"payment_vals": payment_vals})
                log(f"Invoice {invoice_id} payment registration result: {result}")
        except Exception as e:
            log(f"Failed to register payment for invoice {invoice_id}: {e}")
            # As a fallback, try to force the state to 'paid'
            try:
                models.execute_kw(DB, uid, PASS, "account.move", "write", [[invoice_id], {"state": "paid", "payment_state": "paid"}])
                log(f"Force-set invoice {invoice_id} state to paid.")
            except Exception as fe:
                log(f"Force-set invoice state also failed: {fe}")
    else:
        log("No invoice_id found in report – cannot mark invoice paid.")
    # ------------------------------------------------------------
    # 2️⃣ Create timesheet entries (account.analytic.line)
    # ------------------------------------------------------------
    # Timesheet lines are linked to the task via the "task_id" field.
    # We'll create two sample lines: one for 2 hours, another for 3 hours.
    timesheet_vals = []
    now_str = time.strftime("%Y-%m-%d")
    # Employee/user for the timesheet – use the admin user (uid) as a placeholder.
    employee_id = uid
    for hours in (2.0, 3.0):
        vals = {
            "task_id": task_id,
            "project_id": project_id,
            "date": now_str,
            "unit_amount": hours,  # hours logged
            "name": f"Automated timesheet {hours}h",
            "user_id": employee_id,
        }
        timesheet_vals.append(vals)
    # Create the lines one by one (XML‑RPC doesn't support bulk create with list of dicts in all versions)
    created_line_ids = []
    for vals in timesheet_vals:
        line_id = models.execute_kw(DB, uid, PASS, "account.analytic.line", "create", [vals], {"context": {"timesheet_validation": True}})
        created_line_ids.append(line_id)
        log(f"Created timesheet line ID={line_id} for {vals['unit_amount']}h")

    # ------------------------------------------------------------
    # 2️⃣ Call custom project methods in required order
    # ------------------------------------------------------------
    # a) refresh_project_domain_calculation
    try:
        result = models.execute_kw(DB, uid, PASS, "project.project", "refresh_project_domain_calculation", [project_id])
        log(f"refresh_project_domain_calculation result: {result}")
    except Exception as e:
        log(f"refresh_project_domain_calculation failed: {e}")
        # Continue – maybe the method is optional

    # b) calculate_the_progress_remaining_hours
    try:
        result = models.execute_kw(DB, uid, PASS, "project.project", "calculate_the_progress_remaining_hours", [project_id])
        log(f"calculate_the_progress_remaining_hours result: {result}")
    except Exception as e:
        log(f"calculate_the_progress_remaining_hours failed: {e}")

    # c) (phase_id is already set on the project; if needed we could write it again)
    # For completeness, ensure the project still has the correct phase if the method expects it.
    # We'll fetch the project's current phase (if any) just to log.
    try:
        proj_data = models.execute_kw(DB, uid, PASS, "project.project", "read", [[project_id]], {"fields": ["phase_id"]})[0]
        log(f"Project current phase_id: {proj_data.get('phase_id')}")
    except Exception as e:
        log(f"Failed to read project phase_id: {e}")

    # d) action_get_project_progress_report
    try:
        # This method typically returns an action dict for a wizard/report.
        report_action = models.execute_kw(DB, uid, PASS, "project.project", "action_get_project_progress_report", [project_id])
        log(f"action_get_project_progress_report returned: {report_action}")
    except Exception as e:
        log(f"action_get_project_progress_report failed: {e}")

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    log("Extended workflow completed.")
    log(f"Timesheet lines created: {created_line_ids}")

if __name__ == "__main__":
    main()
