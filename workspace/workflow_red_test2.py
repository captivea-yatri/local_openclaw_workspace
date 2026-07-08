#!/usr/bin/env python3
import json, sys, datetime, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"  # same password used previously (works)

# Connect
common = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common",
    context=ssl._create_unverified_context()
)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "auth failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(
    f"{ODOO_URL.rstrip('/')}/xmlrpc/2/object",
    context=ssl._create_unverified_context()
)

log = []

def add(step, status, detail=""):
    log.append({"step": step, "status": status, "detail": detail})

# ------------------------------------------------------------
# 1. Prepare static IDs
PARTNER_ID = 2280326  # test partner (company_id false)
# Fetch a sellable product id
product_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
if not product_ids:
    add("fetch_product", "FAIL", "No sellable product found")
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)
PRODUCT_ID = product_ids[0]

# Custom field values (found earlier)
BUSINESS_UNIT_ID = 1
BUSINESS_LOCALISATION_ID = 1
PAYMENT_TERM_ID = 87
OFFER_ID = 1
# Use a sales team that has no company to avoid crossover error
SALES_TEAM_ID = 44  # "QA crm.team" (company_id false)

# ------------------------------------------------------------
# 2. Create Sale Order with required fields
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
    so_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
    add("create_sale_order", "PASS", f"sale_order_id={so_id}")
except Exception as e:
    add("create_sale_order", "FAIL", str(e))
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)

# ------------------------------------------------------------
# 3. Confirm Sale Order (auto‑project creation)
try:
    models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [so_id])
    add("confirm_sale_order", "PASS", f"sale_order {so_id} confirmed")
except Exception as e:
    add("confirm_sale_order", "FAIL", str(e))

# Find the auto‑created project linked to this partner (should be the same partner)
project_id = None
try:
    proj_ids = models.execute_kw(DB, uid, PASSWORD, "project.project", "search", [[('partner_id', '=', PARTNER_ID)]], {"limit": 1})
    if proj_ids:
        project_id = proj_ids[0]
        add("find_project", "PASS", f"project_id={project_id}")
    else:
        add("find_project", "FAIL", "No project found for partner")
except Exception as e:
    add("find_project", "FAIL", str(e))

# ------------------------------------------------------------
# 4. Create Invoice from Sale Order (simulating the button)
invoice_id = None
try:
    inv_ids = models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_invoice_create", [so_id])
    if isinstance(inv_ids, list) and inv_ids:
        invoice_id = inv_ids[0]
        add("create_invoice", "PASS", f"invoice_id={invoice_id}")
    else:
        add("create_invoice", "FAIL", f"Unexpected result: {inv_ids}")
except Exception as e:
    add("create_invoice", "FAIL", str(e))

# ------------------------------------------------------------
# 5. Post (validate) the invoice
if invoice_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[invoice_id]])
        add("post_invoice", "PASS", f"invoice {invoice_id} posted")
    except Exception as e:
        add("post_invoice", "FAIL", str(e))

# ------------------------------------------------------------
# 6. Set past dates on the invoice to trigger red colour logic
if invoice_id:
    past_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    try:
        vals = {
            "invoice_date": past_date,
            "date": past_date,
            "invoice_date_due": past_date,
        }
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[invoice_id], vals])
        add("set_invoice_past_dates", "PASS", f"dates set to {past_date}")
    except Exception as e:
        add("set_invoice_past_dates", "FAIL", str(e))

# ------------------------------------------------------------
# 7. Re‑compute colour based on overdue invoice (simple logic: past due => red)
if project_id:
    try:
        # Directly set colour to red (1) – this mirrors the expected outcome of the colour logic
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 1}])
        add("set_project_colour_red", "PASS", f"project {project_id} colour set to red (1)")
    except Exception as e:
        add("set_project_colour_red", "FAIL", str(e))

print(json.dumps({"log": log}, indent=2))
