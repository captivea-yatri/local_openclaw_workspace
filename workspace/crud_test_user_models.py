'''Perform CRUD tests for a predefined list of Odoo models.

The script:
1. Loads credentials from `odoo_credentials.json`.
2. Authenticates as the configured user.
3. For each model name supplied in `model_list` it attempts:
   - READ  : `search` (limit 1)
   - CREATE: builds a minimal record using the first required field.
   - WRITE : updates that field on the created (or existing) record.
   - DELETE: removes the created record.
4. Any XML‑RPC Fault or generic exception is captured and stored.
5. Results are written to `crud_user_models_report.json`.

No preliminary `ir.model` lookup is performed – we directly call the methods
and rely on the returned fault to indicate a missing/hidden model.
''' 

import json, sys, xmlrpc.client, os

# ---------------------- Load credentials ----------------------
cred_path = os.path.join(os.path.dirname(__file__), "odoo_credentials.json")
with open(cred_path, "r", encoding="utf8") as f:
    cred = json.load(f)
URL = cred["url"]
DB = cred["db"]
USERNAME = cred["username"]
# Password may be masked; pick the non‑standard key.
PASSWORD = cred.get("password") or next(v for k, v in cred.items() if k not in ("url", "db", "username"))

# ---------------------- RPC helper ----------------------
def rpc(obj, uid, pw, db, method, *args, **kwargs):
    try:
        return obj.execute_kw(db, uid, pw, method, args, kwargs)
    except xmlrpc.client.Fault as f:
        return {"__fault__": str(f)}
    except Exception as e:
        return {"__error__": str(e)}

# ---------------------- Authenticate ----------------------
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    sys.exit(f"❌ Authentication failed for {USERNAME}@{DB}")
print(f"✅ Authenticated UID {uid}")

models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# ---------------------- Models to test (provided by user) ----------------------
model_list = [
    "account.account",
    "account.analytic.account",
    "timesheet.analytic.account",
    "hr.applicant",
    "account.asset",
    "res.partner",
    "hr.employee",
    "hr.employee.public",
    "gamification.challenge",
    "gamification.goal",
    "gamification.goal_finance_information",
    "x_target_adjustment",
    "account.journal",
    "account.move",
    "account.payment",
    "account.tax",
    "crm.lead",
    "product.template",
    "product.product",
    "project.project",
    "project.task",
    "project.project.stage",
    "sale.order",
    "sale.order.line",
    "crm.stage",
    "crm.lost.reason",
    "product.pricelist",
    "website",
    "helpdesk.ticket",
    "helpdesk.team",
    "purchase.order",
    "po.comment",
    "social.post",
    "mail.mass_mailing",
    "marketing.campaign",
    "hr.attendance",
    "go.live.change.request",
    "sign",
    "payroll",
    "hr.leave",
    "ir.attachment"
]

report = {}

for model in model_list:
    result = {"read": None, "create": None, "write": None, "delete": None}

    # ---------- READ ----------
    read_ids = rpc(models, uid, PASSWORD, DB, "search", model, [[]], {"limit": 1})
    if isinstance(read_ids, dict) and ("__fault__" in read_ids or "__error__" in read_ids):
        result["read"] = {"status": "blocked", "error": read_ids.get("__fault__") or read_ids.get("__error__")}
        record_id = None
    else:
        result["read"] = {"status": "allowed" if read_ids else "allowed_no_records"}
        record_id = read_ids[0] if read_ids else None

    # ---------- CREATE ----------
    fields_info = rpc(models, uid, PASSWORD, DB, "fields_get", model, [], {"attributes": ["type", "required", "relation"]})
    if isinstance(fields_info, dict) and ("__fault__" in fields_info or "__error__" in fields_info):
        result["create"] = {"status": "blocked", "error": fields_info.get("__fault__") or fields_info.get("__error__")}
        created_id = None
    else:
        create_vals = {}
        for fname, finfo in fields_info.items():
            if finfo.get("required"):
                ftype = finfo.get("type")
                if ftype == "char":
                    create_vals[fname] = f"test_{model}"
                elif ftype == "integer":
                    create_vals[fname] = 0
                elif ftype == "boolean":
                    create_vals[fname] = False
                elif ftype == "many2one":
                    rel = finfo.get("relation")
                    rel_ids = rpc(models, uid, PASSWORD, DB, "search", rel, [[]], {"limit": 1})
                    if isinstance(rel_ids, list) and rel_ids:
                        create_vals[fname] = rel_ids[0]
                if fname in create_vals:
                    break
        if not create_vals:
            result["create"] = {"status": "skipped", "reason": "no suitable required field"}
            created_id = None
        else:
            created_id = rpc(models, uid, PASSWORD, DB, "create", model, [create_vals])
            if isinstance(created_id, dict) and ("__fault__" in created_id or "__error__" in created_id):
                result["create"] = {"status": "blocked", "error": created_id.get("__fault__") or created_id.get("__error__")}
                created_id = None
            else:
                result["create"] = {"status": "allowed", "id": created_id}

    # ---------- WRITE ----------
    target_id = created_id or record_id
    if target_id:
        write_field = next(iter(create_vals)) if create_vals else None
        if write_field:
            new_val = f"updated_{model}" if isinstance(create_vals[write_field], str) else create_vals[write_field]
            write_res = rpc(models, uid, PASSWORD, DB, "write", model, [[target_id], {write_field: new_val}])
            if isinstance(write_res, dict) and ("__fault__" in write_res or "__error__" in write_res):
                result["write"] = {"status": "blocked", "error": write_res.get("__fault__") or write_res.get("__error__")}
            else:
                result["write"] = {"status": "allowed"}
        else:
            result["write"] = {"status": "skipped", "reason": "no writable field identified"}
    else:
        result["write"] = {"status": "skipped", "reason": "no record to write"}

    # ---------- DELETE ----------
    if created_id:
        del_res = rpc(models, uid, PASSWORD, DB, "unlink", model, [[created_id]])
        if isinstance(del_res, dict) and ("__fault__" in del_res or "__error__" in del_res):
            result["delete"] = {"status": "blocked", "error": del_res.get("__fault__") or del_res.get("__error__")}
        else:
            result["delete"] = {"status": "allowed"}
    else:
        result["delete"] = {"status": "skipped", "reason": "no test record created"}

    report[model] = result

# ---------------------- Write report ----------------------
out_path = os.path.join(os.path.dirname(__file__), "crud_user_models_report.json")
with open(out_path, "w", encoding="utf8") as f:
    json.dump(report, f, indent=2)
print(f"🗂 Report written to {out_path}")
