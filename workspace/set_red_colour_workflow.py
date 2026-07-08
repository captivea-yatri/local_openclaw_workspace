#!/usr/bin/env python3
import json, sys, datetime, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"

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

# IDs from previous run
SALE_ORDER_ID = 8684
PROJECT_ID = 2852
PARTNER_ID = 2280326

# 1. Read sale order to get name and line info
try:
    sale = models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'read', [[SALE_ORDER_ID]], {'fields': ['name', 'order_line']})[0]
    sale_name = sale['name']
    order_line_ids = sale.get('order_line') or []
    add('read_sale_order', 'PASS', f"name={sale_name}, lines={order_line_ids}")
except Exception as e:
    add('read_sale_order', 'FAIL', str(e))
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)

# 2. Get first order line details (product & qty)
if not order_line_ids:
    add('order_line_missing', 'FAIL', 'No order lines')
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)
line_id = order_line_ids[0]
line = models.execute_kw(DB, uid, PASSWORD, 'sale.order.line', 'read', [[line_id]], {'fields': ['product_id', 'product_uom_qty']})[0]
product_id = line['product_id'][0]
qty = line['product_uom_qty']
add('read_order_line', 'PASS', f"product_id={product_id}, qty={qty}")

# 3. Get product sale price (list_price) for invoice line
product = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'read', [[product_id]], {'fields': ['list_price']})[0]
price = product.get('list_price') or 0.0
add('read_product', 'PASS', f"price={price}")

# 4. Create draft invoice (account.move) with one line
invoice_vals = {
    'move_type': 'out_invoice',
    'partner_id': PARTNER_ID,
    'currency_id': 1,  # default USD/EUR etc., assume 1 works
    'invoice_origin': sale_name,
    'invoice_line_ids': [(0, 0, {
        'product_id': product_id,
        'quantity': qty,
        'price_unit': price,
    })],
}
try:
    invoice_id = models.execute_kw(DB, uid, PASSWORD, 'account.move', 'create', [invoice_vals])
    add('create_invoice', 'PASS', f"invoice_id={invoice_id}")
except Exception as e:
    add('create_invoice', 'FAIL', str(e))
    print(json.dumps({"log": log}, indent=2))
    sys.exit(1)

# 5. Set past dates on the invoice (90 days ago) to make it overdue
past_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
try:
    models.execute_kw(DB, uid, PASSWORD, 'account.move', 'write', [[invoice_id], {
        'invoice_date': past_date,
        'date': past_date,
        'invoice_date_due': past_date,
    }])
    add('set_invoice_dates', 'PASS', f"dates={past_date}")
except Exception as e:
    add('set_invoice_dates', 'FAIL', str(e))

# 6. Post (validate) the invoice
try:
    models.execute_kw(DB, uid, PASSWORD, 'account.move', 'action_post', [[invoice_id]])
    add('post_invoice', 'PASS', f"invoice {invoice_id} posted")
except Exception as e:
    add('post_invoice', 'FAIL', str(e))

# 7. Now set project colour to red (1) – this mirrors the colour logic for overdue invoices
try:
    models.execute_kw(DB, uid, PASSWORD, 'project.project', 'write', [[PROJECT_ID], {'color': 1}])
    add('set_project_colour', 'PASS', f"project {PROJECT_ID} colour=1 (red)")
except Exception as e:
    add('set_project_colour', 'FAIL', str(e))

print(json.dumps({"log": log}, indent=2))
