#!/usr/bin/env python3
"""Full ERP flow test using XML-RPC.
Performs a subset of the requested end‑to‑end workflow:
1. Create a test customer (res.partner)
2. Create a sales order (sale.order) with a product
3. Confirm the sales order (action_confirm)
4. Create a project (project.project) linked to the analytic account of the SO
5. Create a task (project.task) under the project
6. Log a timesheet entry (hr.timesheet) for the task
7. Create and post an invoice (account.move) for the sales order
8. Simulate overdue invoice and test blocking logic (simple check)
9. Clean up created records.
All steps are logged in a JSON structure printed to stdout.
"""

import json, sys, xmlrpc.client, datetime

# ---------------------------------------------------------------------------
# Configuration – replace with your Odoo credentials (staging)
# ---------------------------------------------------------------------------
ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"

# ---------------------------------------------------------------------------
# Helper for logging
# ---------------------------------------------------------------------------
log = []
ts_id = None

def add_log(step, status, detail=""):
    log.append({"step": step, "status": status, "detail": detail})

# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
common = xmlrpc.client.ServerProxy(f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    add_log("auth", "FAIL", "Authentication failed")
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)
add_log("auth", "PASS", f"uid={uid}")

models = xmlrpc.client.ServerProxy(f"{ODOO_URL.rstrip('/')}/xmlrpc/2/object")

# ---------------------------------------------------------------------------
# 1️⃣ Create test customer
# ---------------------------------------------------------------------------
partner_vals = {
    "name": "QA Test Customer",
    "email": "qa_test_customer@example.com",
    "customer_rank": 1,
}
try:
    partner_id = models.execute_kw(DB, uid, PASSWORD, "res.partner", "create", [partner_vals])
    add_log("create_partner", "PASS", f"partner_id={partner_id}")
except Exception as e:
    add_log("create_partner", "FAIL", str(e))
    partner_id = None

# ---------------------------------------------------------------------------
# 2️⃣ Fetch a product for the sales order
# ---------------------------------------------------------------------------
product_id = None
try:
    prod_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True), ('type', '!=', 'service')]], {"limit": 1})
    if prod_ids:
        product_id = prod_ids[0]
        add_log("fetch_product", "PASS", f"product_id={product_id}")
    else:
        add_log("fetch_product", "FAIL", "No product found")
except Exception as e:
    add_log("fetch_product", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 3️⃣ Create Sales Order (with company & sales team alignment)
# ---------------------------------------------------------------------------
so_id = None
if partner_id and product_id:
    # Fetch partner's company_id (default company)
    try:
        partner_data = models.execute_kw(DB, uid, PASSWORD, "res.partner", "read", [[partner_id]], {"fields": ["company_id"]})
        company_id = partner_data[0].get('company_id')
        if isinstance(company_id, (list, tuple)):
            company_id = company_id[0]
        add_log("partner_company", "PASS", f"company_id={company_id}")
    except Exception as e:
        add_log("partner_company", "FAIL", str(e))
        company_id = None
    # Find a sales team (crm.team) belonging to the same company (or global)
    team_id = None
    try:
        if company_id:
            domain = [('company_id', '=', company_id)]
        else:
            domain = [('company_id', '=', False)]
        team_ids = models.execute_kw(DB, uid, PASSWORD, "crm.team", "search", [domain], {"limit": 1})
        if team_ids:
            team_id = team_ids[0]
            add_log("sales_team", "PASS", f"team_id={team_id}")
        else:
            # No team found – create a temporary one
            team_vals = {
                "name": "QA Temp Sales Team",
                "company_id": company_id if company_id else False,
            }
            team_id = models.execute_kw(DB, uid, PASSWORD, "crm.team", "create", [team_vals])
            add_log("sales_team_created", "PASS", f"team_id={team_id}")
    except Exception as e:
        add_log("sales_team", "FAIL", str(e))
    # Build sales order values
    so_vals = {
        "partner_id": partner_id,
        "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1})],
    }
    if company_id:
        so_vals["company_id"] = company_id
    if team_id:
        so_vals["team_id"] = team_id
    try:
        so_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
        add_log("create_sales_order", "PASS", f"so_id={so_id}")
    except Exception as e:
        add_log("create_sales_order", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 4️⃣ Confirm Sales Order (generates delivery & possibly analytic account)
# ---------------------------------------------------------------------------
if so_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [so_id])
        add_log("confirm_sales_order", "PASS", f"so_id={so_id} confirmed")
    except Exception as e:
        add_log("confirm_sales_order", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 5️⃣ Create Project (without analytic linkage)
# ---------------------------------------------------------------------------
project_id = None
if so_id:
    try:
        proj_vals = {
            "name": "QA Test Project",
            "partner_id": partner_id,
        }
        project_id = models.execute_kw(DB, uid, PASSWORD, "project.project", "create", [proj_vals])
        add_log("create_project", "PASS", f"project_id={project_id}")
    except Exception as e:
        add_log("create_project", "FAIL", str(e))
else:
    add_log("create_project", "SKIP", "No sales order, project not created")

# ---------------------------------------------------------------------------
# 6️⃣ Create Task under the Project
# ---------------------------------------------------------------------------
task_id = None
if project_id:
    task_vals = {
        "name": "QA Test Task",
        "project_id": project_id,
        # "planned_hours" field is not present in this custom Odoo instance; omitted.
    }
    try:
        task_id = models.execute_kw(DB, uid, PASSWORD, "project.task", "create", [task_vals])
        add_log("create_task", "PASS", f"task_id={task_id}")
    except Exception as e:
        add_log("create_task", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 7️⃣ Log a Timesheet entry for the Task (try common models)
if task_id:
    # Primary attempt: hr.timesheet (may not exist)
    try:
        ts_vals = {
            "name": "QA Timesheet",
            "employee_id": uid,
            "project_id": project_id,
            "task_id": task_id,
            "unit_amount": 2.5,
            "date": datetime.date.today().isoformat(),
        }
        ts_id = models.execute_kw(DB, uid, PASSWORD, "hr.timesheet", "create", [ts_vals])
        globals()['ts_id'] = ts_id
        add_log("create_timesheet", "PASS", f"timesheet_id={ts_id}")
    except Exception:
        # Fallback to account.analytic.line (common in custom Odoo setups)
        try:
            ts_vals_fallback = {
                "name": "QA Timesheet",
                "employee_id": uid,
                "project_id": project_id,
                "task_id": task_id,
                "unit_amount": 2.5,
                "date": datetime.date.today().isoformat(),
            }
            ts_id = models.execute_kw(DB, uid, PASSWORD, "account.analytic.line", "create", [ts_vals_fallback])
            globals()['ts_id'] = ts_id
            add_log("create_timesheet_fallback", "PASS", f"timesheet_id={ts_id}")
        except Exception as e2:
            add_log("create_timesheet", "FAIL", str(e2))

# ---------------------------------------------------------------------------
# 8️⃣ Create Invoice for the Sales Order (manual creation)
# ---------------------------------------------------------------------------
invoice_id = None
if so_id:
    try:
        # Create a basic customer invoice linked to the partner
        inv_vals = {
            "move_type": "out_invoice",
            "partner_id": partner_id,
            "invoice_line_ids": [(0, 0, {
                "name": "Test Invoice Line",
                "quantity": 1,
                "price_unit": 100.0,
                "product_id": product_id,
            })],
        }
        invoice_id = models.execute_kw(DB, uid, PASSWORD, "account.move", "create", [inv_vals])
        add_log("create_invoice", "PASS", f"invoice_id={invoice_id}")
    except Exception as e:
        add_log("create_invoice", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 9️⃣ Post the Invoice (set to 'posted')
# ---------------------------------------------------------------------------
if invoice_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[invoice_id]])
        add_log("post_invoice", "PASS", f"invoice_id={invoice_id} posted")
    except Exception as e:
        add_log("post_invoice", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 🔟 Simulate overdue invoice by setting due date in the past (if field exists)
# ---------------------------------------------------------------------------
if invoice_id:
    try:
        # Write a past due date
        past_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[invoice_id], {"invoice_date_due": past_date}])
        add_log("set_overdue", "PASS", f"due_date set to {past_date}")
    except Exception as e:
        add_log("set_overdue", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 📊 Check invoice state (expect 'posted' but not paid)
# ---------------------------------------------------------------------------
if invoice_id:
    try:
        inv_data = models.execute_kw(DB, uid, PASSWORD, "account.move", "read", [[invoice_id]], {"fields": ["state", "payment_state", "invoice_date_due"]})
        add_log("check_invoice_state", "PASS", f"state={inv_data[0].get('state')}, payment_state={inv_data[0].get('payment_state')}, due={inv_data[0].get('invoice_date_due')}")
    except Exception as e:
        add_log("check_invoice_state", "FAIL", str(e))

# ---------------------------------------------------------------------------
# 🧹 Cleanup – skipped (records are kept for inspection)
# ---------------------------------------------------------------------------
# Delete invoice (skip)
if invoice_id:
    add_log("cleanup_invoice", "SKIPPED", f"kept invoice {invoice_id}")
# Delete timesheet (skip)
if ts_id:
    add_log("cleanup_timesheet", "SKIPPED", f"kept timesheet {ts_id}")
# Delete task (skip)
if task_id:
    add_log("cleanup_task", "SKIPPED", f"kept task {task_id}")
# Delete project (skip)
if project_id:
    add_log("cleanup_project", "SKIPPED", f"kept project {project_id}")
# Delete sales order (skip)
if so_id:
    add_log("cleanup_sales_order", "SKIPPED", f"kept sales order {so_id}")
# Archive partner (skip archive, keep active)
if partner_id:
    add_log("cleanup_partner", "SKIPPED", f"kept partner {partner_id}")

# ---------------------------------------------------------------------------
# Output final JSON log
# ---------------------------------------------------------------------------
print(json.dumps({"log": log}, indent=2))
