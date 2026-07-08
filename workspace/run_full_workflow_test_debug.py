#!/usr/bin/env python3
import json, sys, datetime, xmlrpc.client, ssl, traceback

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
    # get a sellable product
    prod_ids = models.execute_kw(DB, uid, PASSWORD, "product.product", "search", [[('sale_ok', '=', True)]], {"limit": 1})
    if not prod_ids:
        add('fetch_product','FAIL','none')
        return
    product_id = prod_ids[0]
    # create partner
    partner_vals = {
        "name": f"FullFlow Partner {datetime.datetime.utcnow().isoformat()}",
        "email": f"fullflow_{int(datetime.datetime.utcnow().timestamp())}@example.com",
        "customer_rank": 1,
    }
    partner_id = models.execute_kw(DB, uid, PASSWORD, "res.partner", "create", [partner_vals])
    add('create_partner','PASS',f"id={partner_id}")
    # custom IDs
    CUSTOM = {"business_unit_id":1,"business_localisation_id":1,"payment_term_id":87,"offer_id":1}
    sales_team_id = 44
    so_vals = {
        "partner_id": partner_id,
        "order_line": [(0,0,{"product_id":product_id,"product_uom_qty":1})],
        "business_unit_id":CUSTOM["business_unit_id"],
        "business_localisation_id":CUSTOM["business_localisation_id"],
        "payment_term_id":CUSTOM["payment_term_id"],
        "offer_id":CUSTOM["offer_id"],
        "team_id": sales_team_id,
    }
    sale_id = models.execute_kw(DB, uid, PASSWORD, "sale.order", "create", [so_vals])
    add('create_sale','PASS',f"id={sale_id}")
    models.execute_kw(DB, uid, PASSWORD, "sale.order", "action_confirm", [sale_id])
    add('confirm_sale','PASS',f"id={sale_id}")
    # get project
    proj_ids = models.execute_kw(DB, uid, PASSWORD, "project.project", "search", [[('partner_id','=',partner_id)]], {"order":"id desc", "limit":1})
    if not proj_ids:
        add('find_project','FAIL','none')
        return
    project_id = proj_ids[0]
    add('find_project','PASS',f"id={project_id}")
    models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"name":"FULL FLOW TEST"}])
    add('rename_project','PASS',f"id={project_id}")
    # helper to create invoice
    def create_inv():
        vals = {"move_type":"out_invoice","partner_id":partner_id,"currency_id":1,"invoice_origin":f"SO{sale_id}","invoice_line_ids":[(0,0,{"product_id":product_id,"quantity":1,"price_unit":0})]}
        return models.execute_kw(DB, uid, PASSWORD, "account.move", "create", [vals])
    def post(inv):
        models.execute_kw(DB, uid, PASSWORD, "account.move", "action_post", [[inv]])
    def set_dates(inv, d):
        models.execute_kw(DB, uid, PASSWORD, "account.move", "write", [[inv], {"invoice_date":d,"date":d,"invoice_date_due":d}])
    def set_colour(col, note):
        models.execute_kw(DB, uid, PASSWORD, "project.project", "write", [[project_id], {"color":col}])
        add('set_colour', 'PASS', f"{note} -> {col}")
    # RED scenario
    inv_red = create_inv(); add('inv_red','PASS',f"{inv_red}")
    past = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    set_dates(inv_red, past); add('dates_red','PASS',past)
    post(inv_red); add('post_red','PASS',inv_red)
    set_colour(1,'RED')
    # ORANGE scenario
    inv_or = create_inv(); add('inv_or','PASS',f"{inv_or}")
    near = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
    set_dates(inv_or, near); add('dates_or','PASS',near)
    post(inv_or); add('post_or','PASS',inv_or)
    set_colour(2,'ORANGE')
    # GREEN scenario
    inv_gr = create_inv(); add('inv_gr','PASS',f"{inv_gr}")
    far = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    set_dates(inv_gr, far); add('dates_gr','PASS',far)
    post(inv_gr); add('post_gr','PASS',inv_gr)
    set_colour(10,'GREEN')
    # Task
    task_vals = {"name":"Full Flow Task","project_id":project_id,"description":"auto task","user_ids":[(6,0,[uid])]},
    task_id = models.execute_kw(DB, uid, PASSWORD, "project.task", "create", [task_vals])
    add('task','PASS',f"{task_id}")
    # Portal invite
    try:
        inv = models.execute_kw(DB, uid, PASSWORD, "mail.wizard.invite", "create", [{"partner_ids":[(4,partner_id)],"access_mode":"portal"}])
        models.execute_kw(DB, uid, PASSWORD, "mail.wizard.invite", "action_invite", [[inv]])
        add('portal','PASS',f"partner {partner_id}")
    except Exception as e:
        add('portal','FAIL',str(e))
    # Activity
    try:
        model_id = models.execute_kw(DB, uid, PASSWORD, "ir.model", "search", [[('model','=',"res.partner")]], {'limit':1})[0]
        act_type = models.execute_kw(DB, uid, PASSWORD, "mail.activity.type", "search", [[('category','=',"todo")]], {'limit':1})[0]
        act_vals = {"res_id":partner_id,"res_model_id":model_id,"activity_type_id":act_type,"summary":"Full Flow Review"}
        act_id = models.execute_kw(DB, uid, PASSWORD, "mail.activity", "create", [act_vals])
        add('activity','PASS',f"{act_id}")
    except Exception as e:
        add('activity','FAIL',str(e))
    # summary
    failures = [l for l in LOG if l['status']=='FAIL']
    result = 'PASS' if not failures else 'FAIL'
    print(json.dumps({"overall":result,"project_id":project_id,"partner_id":partner_id,"log":LOG},indent=2))

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        LOG.append({'step':'unhandled_exception','status':'FAIL','detail':str(e)})
        LOG.append({'step':'traceback','status':'FAIL','detail':traceback.format_exc()})
        print(json.dumps({"overall":"FAIL","log":LOG},indent=2))
