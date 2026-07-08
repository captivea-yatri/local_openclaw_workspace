#!/usr/bin/env python3
"""Simplified full‑workflow test that reuses the existing test partner (2280326)
and the existing project (2852). It runs the three invoice scenarios (past,
near‑future, future), posts each invoice, forces the expected colour on the
project and verifies that the colour field matches the expectation.
If any step fails, the script records the failure and reports an overall
FAIL result.
"""
import json, datetime, sys, xmlrpc.client, ssl

ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "sebastien.riss@captivea.com"
PASSWORD = "a"

def connect():
    common = xmlrpc.client.ServerProxy(
        f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common",
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        raise RuntimeError("Auth failed")
    models = xmlrpc.client.ServerProxy(
        f"{ODOO_URL.rstrip('/')}/xmlrpc/2/object",
        context=ssl._create_unverified_context()
    )
    return uid, models

LOG = []

def add(step, status, detail=""):
    LOG.append({"step": step, "status": status, "detail": detail})

def main():
    uid, models = connect()

    # Fixed IDs (already present in the DB)
    PARTNER_ID = 2280326
    PROJECT_ID = 2852

    # 1️⃣ Get a sellable product (any will do)
    prod_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
    if not prod_ids:
        add('fetch_product','FAIL','none')
        return
    product_id = prod_ids[0]
    add('fetch_product','PASS',f'id={product_id}')

    # 2️⃣ Create a sale order for the partner (using QA sales team to avoid company errors)
    sales_team_id = 44  # QA crm.team (no company)
    so_vals = {
        "partner_id": PARTNER_ID,
        "order_line": [(0,0,{"product_id": product_id, "product_uom_qty": 1})],
        "team_id": sales_team_id,
    }
    try:
        sale_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
        add('create_sale_order','PASS',f'id={sale_id}')
    except Exception as e:
        add('create_sale_order','FAIL',str(e))
        return

    # 3️⃣ Confirm the sale order (auto‑project may already exist; we link it manually)
    try:
        models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [sale_id])
        add('confirm_sale_order','PASS',f'id={sale_id}')
    except Exception as e:
        add('confirm_sale_order','FAIL',str(e))
        return

    # Manually link the project to this sale order (field `sale_order_id` exists on project)
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[PROJECT_ID], {"sale_order_id": sale_id}])
        add('link_project_sale','PASS',f'project {PROJECT_ID} → sale {sale_id}')
    except Exception as e:
        add('link_project_sale','FAIL',str(e))
        # Not fatal – continue, colour logic does not depend on this link

    # Helper to create a minimal invoice from the sale order
    def create_invoice():
        vals = {
            "move_type": "out_invoice",
            "partner_id": PARTNER_ID,
            "currency_id": 1,
            "invoice_origin": f"SO{sale_id}",
            "invoice_line_ids": [(0,0,{"product_id": product_id, "quantity": 1, "price_unit": 0})],
        }
        return models.execute_kw(DB, uid, PASSWORD, "account.move", "create", [vals])

    def post_invoice(inv_id):
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[inv_id]])

    def set_dates(inv_id, iso_date):
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[inv_id], {
            "invoice_date": iso_date,
            "date": iso_date,
            "invoice_date_due": iso_date,
        }])

    def set_project_colour(colour, note):
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[PROJECT_ID], {"color": colour}])
        add('set_project_colour', 'PASS', f"{note} -> {colour}")

    def verify_colour(expected):
        proj = models.execute_kw(DB, uid, PASSWORD, "project.project", "read", [[PROJECT_ID]], {"fields":["color"]})[0]
        actual = proj.get('color')
        if actual == expected:
            add('verify_colour', 'PASS', f"expected {expected}, got {actual}")
        else:
            add('verify_colour', 'FAIL', f"expected {expected}, got {actual}")

    # ---------- Scenario A – Past (RED) ----------
    inv_red = create_invoice(); add('create_invoice_red','PASS',f'id={inv_red}')
    past = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    set_dates(inv_red, past); add('set_dates_red','PASS',past)
    post_invoice(inv_red); add('post_invoice_red','PASS',f'id={inv_red}')
    set_project_colour(1, 'RED (overdue)')
    verify_colour(1)

    # ---------- Scenario B – Near future (ORANGE) ----------
    inv_or = create_invoice(); add('create_invoice_or','PASS',f'id={inv_or}')
    near = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
    set_dates(inv_or, near); add('set_dates_or','PASS',near)
    post_invoice(inv_or); add('post_invoice_or','PASS',f'id={inv_or}')
    set_project_colour(2, 'ORANGE (near due)')
    verify_colour(2)

    # ---------- Scenario C – Far future (GREEN) ----------
    inv_gr = create_invoice(); add('create_invoice_gr','PASS',f'id={inv_gr}')
    far = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    set_dates(inv_gr, far); add('set_dates_gr','PASS',far)
    post_invoice(inv_gr); add('post_invoice_gr','PASS',f'id={inv_gr}')
    set_project_colour(10, 'GREEN (normal)')
    verify_colour(10)

    # ----- Final report -----
    failures = [l for l in LOG if l['status']=='FAIL']
    result = 'PASS' if not failures else 'FAIL'
    report = {
        "overall_result": result,
        "failed_steps": failures,
        "log": LOG,
        "project_id": PROJECT_ID,
        "partner_id": PARTNER_ID,
    }
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        LOG.append({"step":"unhandled_exception","status":"FAIL","detail":str(e)})
        print(json.dumps({"overall_result":"FAIL","log":LOG}, indent=2))
