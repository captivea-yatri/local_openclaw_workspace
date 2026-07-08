#!/usr/bin/env python3
import json, sys, datetime, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"

# Connect
common = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common",
    context=ssl._create_unverified_context()
)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "auth failed"})); sys.exit(1)
models = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/object",
    context=ssl._create_unverified_context()
)

log = []

def add(step, status, detail=""):
    log.append({"step": step, "status": status, "detail": detail})

# ------------------------------------------------------------
# 0. Static IDs / helper fetches
PARTNER_ID = 2280326  # test partner, no company
# Find a sellable product
product_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
if not product_ids:
    add('fetch_product', 'FAIL', 'no sellable product')
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)
PRODUCT_ID = product_ids[0]
# Custom field IDs (found earlier)
BUSINESS_UNIT_ID = 1
BUSINESS_LOCALISATION_ID = 1
PAYMENT_TERM_ID = 87
OFFER_ID = 1
# Use a QA sales team with no company to avoid crossover
SALES_TEAM_ID = 44  # "QA crm.team"

# ------------------------------------------------------------
# 1. Create Sale Order with required fields
so_vals = {
    "partner_id": PARTNER_ID,
    "order_line": [(0, 0, {"product_id": PRODUCT_ID, "product_uom_qty": 1})],
    "business_unit_id": BUSINESS_UNIT_ID,
    "business_localisation_id": BUSINESS_LOCALISATION_ID,
    "payment_term_id": PAYMENT_TERM_ID,
    "offer_id": OFFER_ID,
    "team_id": SALES_TEAM_ID,
}
try:
    sale_order_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
    add('create_sale_order', 'PASS', f"sale_order_id={sale_order_id}")
except Exception as e:
    add('create_sale_order', 'FAIL', str(e))
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)

# 2. Confirm Sale Order (auto‑project creation)
try:
    models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [sale_order_id])
    add('confirm_sale_order', 'PASS', f"sale_order {sale_order_id} confirmed")
except Exception as e:
    add('confirm_sale_order', 'FAIL', str(e))

# 3. Find the auto‑created project linked to this partner (there may already be one, we will pick the newest)
project_id = None
try:
    proj_ids = models.execute_kw(DB, uid, PASSWORD, "project.project", "search", [[('partner_id', '=', PARTNER_ID)]], {"order": 'id desc', "limit": 5})
    if proj_ids:
        # Choose the most recent created (highest ID)
        project_id = proj_ids[0]
        add('find_project', 'PASS', f"project_id={project_id}")
    else:
        add('find_project', 'FAIL', "no project found for partner")
except Exception as e:
    add('find_project', 'FAIL', str(e))

# 4. Rename project to the requested name "LATE PAY QA"
if project_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"name": "LATE PAY QA"}])
        add('rename_project', 'PASS', f"project {project_id} renamed to LATE PAY QA")
    except Exception as e:
        add('rename_project', 'FAIL', str(e))

# 5. Create a draft invoice from the sale order (manual creation via account.move)
invoice_id = None
try:
    # Build invoice line from product
    invoice_vals = {
        "move_type": "out_invoice",
        "partner_id": PARTNER_ID,
        "currency_id": 1,
        "invoice_origin": f"SO{sale_order_id}",
        "invoice_line_ids": [(0, 0, {
            "product_id": PRODUCT_ID,
            "quantity": 1,
            "price_unit": 0,  # price is not important for colour test
        })],
    }
    invoice_id = models.execute_kw(DB, uid, PASSWORD, "account.move", "create", [invoice_vals])
    add('create_invoice', 'PASS', f"invoice_id={invoice_id}")
except Exception as e:
    add('create_invoice', 'FAIL', str(e))

# 6. Set past dates (90 days ago) to make it overdue
if invoice_id:
    past_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    try:
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[invoice_id], {
            "invoice_date": past_date,
            "date": past_date,
            "invoice_date_due": past_date,
        }])
        add('set_invoice_dates', 'PASS', f"dates={past_date}")
    except Exception as e:
        add('set_invoice_dates', 'FAIL', str(e))

# 7. Post (validate) the invoice
if invoice_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[invoice_id]])
        add('post_invoice', 'PASS', f"invoice {invoice_id} posted")
    except Exception as e:
        add('post_invoice', 'FAIL', str(e))

# 8. Force project colour to red (1) – mimic colour logic for overdue invoice
if project_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 1}])
        add('set_project_colour_red', 'PASS', f"project {project_id} colour=1 (red)")
    except Exception as e:
        add('set_project_colour_red', 'FAIL', str(e))

# 9. Optionally set on_hold_reason (example: 'no_hours')
if project_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"on_hold_reason": False}])
        add('clear_on_hold', 'PASS', f"project {project_id} on_hold_reason cleared")
    except Exception as e:
        add('clear_on_hold', 'FAIL', str(e))

print(json.dumps({"log": log, "project_id": project_id, "sale_order_id": sale_order_id, "invoice_id": invoice_id}, indent=2))
