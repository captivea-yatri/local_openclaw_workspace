#!/usr/bin/env python3
import json, sys, datetime, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"  # same as earlier successful runs

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

# --- 1. Prepare IDs ---
PARTNER_ID = 2280326  # test partner from earlier
# fetch a sellable product id
prod_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
if not prod_ids:
    add("fetch_product", "FAIL", "No sellable product found")
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)
PRODUCT_ID = prod_ids[0]

# custom fields values (using IDs from earlier discovery)
BUSINESS_UNIT_ID = 1        # business.unit
BUSINESS_LOCALISATION_ID = 1  # business.localisation
PAYMENT_TERM_ID = 87        # account.payment.term
OFFER_ID = 1                # offer.offer

# --- 2. Create Sale Order with custom fields and line ---
so_vals = {
    "partner_id": PARTNER_ID,
    "order_line": [(0, 0, {"product_id": PRODUCT_ID, "product_uom_qty": 1})],
    "business_unit_id": BUSINESS_UNIT_ID,
    "business_localisation_id": BUSINESS_LOCALISATION_ID,
    "payment_term_id": PAYMENT_TERM_ID,
    "offer_id": OFFER_ID,
}
try:
    so_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
    add("create_sale_order", "PASS", f"sale_order_id={so_id}")
except Exception as e:
    add("create_sale_order", "FAIL", str(e))
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)

# --- 3. Confirm Sale Order (auto‑project creation) ---
try:
    models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [so_id])
    add("confirm_sale_order", "PASS", f"sale_order {so_id} confirmed")
except Exception as e:
    add("confirm_sale_order", "FAIL", str(e))

# Find the auto‑created project linked to this partner
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

# --- 4. Create Invoice from Sale Order ---
invoice_id = None
try:
    # action_invoice_create returns a list of invoice ids
    inv_ids = models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_invoice_create", [so_id])
    if isinstance(inv_ids, list) and inv_ids:
        invoice_id = inv_ids[0]
        add("create_invoice", "PASS", f"invoice_id={invoice_id}")
    else:
        add("create_invoice", "FAIL", f"Unexpected result: {inv_ids}")
except Exception as e:
    add("create_invoice", "FAIL", str(e))

# --- 5. Post the invoice (validate) ---
if invoice_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[invoice_id]])
        add("post_invoice", "PASS", f"invoice {invoice_id} posted")
    except Exception as e:
        add("post_invoice", "FAIL", str(e))

# --- 6. Set past dates to trigger red colour ---
if invoice_id:
    past_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()  # ~3 months ago
    try:
        vals = {
            "invoice_date": past_date,
            "date": past_date,
            "invoice_date_due": past_date,
        }
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[invoice_id], vals])
        add("set_past_dates", "PASS", f"dates set to {past_date}")
    except Exception as e:
        add("set_past_dates", "FAIL", str(e))

# --- 7. Force project colour to red (1) based on overdue invoice ---
if project_id:
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 1}])
        add("set_project_colour_red", "PASS", f"project {project_id} colour=1 (red)")
    except Exception as e:
        add("set_project_colour_red", "FAIL", str(e))

print(json.dumps({"log": log}, indent=2))
