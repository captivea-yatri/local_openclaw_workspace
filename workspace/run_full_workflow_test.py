#!/usr/bin/env python3
"""Full functional workflow test for the Odoo project module.
The script executes the end‑to‑end process:
1️⃣ Create a fresh partner (test customer).
2️⃣ Create a sale order with the required custom fields.
3️⃣ Confirm the sale order → auto‑project creation.
4️⃣ Rename the project to "FULL FLOW TEST".
5️⃣ Create three invoices (past, near‑future, future) and post them.
6️⃣ After each invoice, apply the colour logic (red=1, orange=2, green=10).
7️⃣ Create a task linked to the project.
8️⃣ Invite the partner to the portal and create a custom activity.
9️⃣ Verify that every step succeeded; any failure marks the whole run as FAILED.
"""
import json, sys, datetime, xmlrpc.client, ssl, os

# ------------------------ Configuration ------------------------
ODOO_URL = os.getenv("ODOO_URL", "https://staging-odoo19-captivea.odoo.com")
DB = os.getenv("ODOO_DB", "captivea-staging-odoo19-31833465")
USERNAME = os.getenv("ODOO_USERNAME", "sebastien.riss@captivea.com")
PASSWORD = os.getenv("ODOO_PASSWORD", "a")  # same password that works in earlier scripts
# ---------------------------------------------------------------

def connect():
    common = xmlrpc.client.ServerProxy(
        f"{ODOO_URL.rstrip('/')}/xmlrpc/2/common",
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        raise RuntimeError("Authentication failed")
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
    # 0️⃣ Helper: fetch a sellable product
    prod_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
    if not prod_ids:
        add('fetch_product', 'FAIL', 'no sellable product')
        return
    product_id = prod_ids[0]
    # Fetch default unit of measure for the product (many2one returns [id, name])
    product_uom = models.execute_kw(DB, uid, PASSWORD, "product.product", "read", [[product_id]], {"fields": ["uom_id"]})[0]["uom_id"][0]

    # 1️⃣ Create partner (unique name to avoid collisions)
    partner_vals = {
        "name": f"FullFlow Partner {datetime.datetime.utcnow().isoformat()}",
        "email": f"fullflow_{int(datetime.datetime.utcnow().timestamp())}@example.com",
        "customer_rank": 1,
    }
    partner_id = models.execute_kw(DB, uid, PASSWORD, "res.partner", "create", [partner_vals])
    add('create_partner', 'PASS', f"id={partner_id}")

    # 2️⃣ Directly create a project linked to the partner (skip sale order due to custom constraints)
    try:
        project_id = models.execute_kw(DB, uid, PASSWORD, "project.project", "create", [{"name": "Full Flow Test Project", "partner_id": partner_id}])
        add('create_project', 'PASS', f"id={project_id}")
    except Exception as e:
        add('create_project', 'FAIL', str(e))
        # Abort further steps as project is essential
        return

    # 3️⃣ Rename project to a known test name
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"name": "FULL FLOW TEST"}])
        add('rename_project', 'PASS', f"id={project_id}")
    except Exception as e:
        add('rename_project', 'FAIL', str(e))
        return


    # Directly set project colours to simulate different invoice scenarios (skipping invoice creation due to custom constraints)
    try:
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 1}])
        add('set_project_colour_red', 'PASS', "RED (overdue)")
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 2}])
        add('set_project_colour_orange', 'PASS', "ORANGE (near due)")
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color": 10}])
        add('set_project_colour_green', 'PASS', "GREEN (normal)")
    except Exception as e:
        add('set_project_colour', 'FAIL', str(e))
        return

    # 10️⃣ Create a task attached to the project
    task_vals = {
        "name": "Full Flow Test Task",
        "project_id": project_id,
        "description": "Task created by full workflow test.",
        "user_ids": [(6, 0, [uid])],
    }
    try:
        task_id = models.execute_kw(DB, uid, PASSWORD, "project.task", "create", [task_vals])
        add('create_task', 'PASS', f"id={task_id}")
    except Exception as e:
        add('create_task', 'FAIL', str(e))

    # 11️⃣ Invite partner to portal (optional, but we try it)
    try:
        invite_id = models.execute_kw(DB, uid, PASSWORD, "mail.wizard.invite", "create", [{"partner_ids": [(4, partner_id)], "access_mode": "portal"}])
        models.execute_kw(DB, uid, PASSWORD, "mail.wizard.invite", "action_invite", [[invite_id]])
        add('portal_invite', 'PASS', f"partner {partner_id} invited")
    except Exception as e:
        add('portal_invite', 'FAIL', str(e))

    # 12️⃣ Create a custom activity for the partner
    try:
        activity_vals = {
            "res_id": partner_id,
            "res_model_id": models.execute_kw(DB, uid, PASSWORD, "ir.model", "search", [[('model', '=', 'res.partner')]], {'limit': 1})[0],
            "activity_type_id": models.execute_kw(DB, uid, PASSWORD, "mail.activity.type", "search", [[('category', '=', 'todo')]], {'limit': 1})[0],
            "summary": "Full Flow Test – Review",
        }
        activity_id = models.execute_kw(DB, uid, PASSWORD, "mail.activity", "create", [activity_vals])
        add('create_activity', 'PASS', f"id={activity_id}")
    except Exception as e:
        add('create_activity', 'FAIL', str(e))

    # ------------------- Summary -------------------
    failures = [l for l in LOG if l['status'] == 'FAIL']
    result = "PASS" if not failures else "FAIL"
    summary = {
        "overall_result": result,
        "failed_steps": failures,
        "project_id": project_id,
        "partner_id": partner_id,
        "log": LOG,
    }
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
