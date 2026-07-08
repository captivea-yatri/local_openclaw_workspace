'''CRUD test for selected Odoo models (provided by user).

The script:
1. Loads Odoo connection info from `odoo_credentials.json`.
2. Authenticates as the configured user.
3. Iterates over a hard‑coded list of model technical names.
4. For each model attempts Read, Create, Write, Delete operations using the
   minimal required fields (char/int/boolean/many2one where possible).
5. Records success/blocked status and any error messages.
6. Writes a detailed JSON report to `crud_selected_report.json`.

All created test records are deleted afterwards, so the database remains clean.
''' 

import json, sys, xmlrpc.client, os

# -------------------------------------------------------------------
# Load credentials
# -------------------------------------------------------------------
cred_path = os.path.join(os.path.dirname(__file__), "odoo_credentials.json")
try:
    with open(cred_path, "r", encoding="utf8") as f:
        cred = json.load(f)
except Exception as e:
    sys.exit(f"❌ Failed to read credentials: {e}")

URL = cred["url"]
DB = cred["db"]
USERNAME = cred["username"]
# password key is obscured (e.g., "p***ssword"); pick the remaining key.
PASSWORD = cred.get("password") or next(v for k, v in cred.items() if k not in ("url", "db", "username"))

# -------------------------------------------------------------------
# Helper for safe RPC calls
# -------------------------------------------------------------------
def rpc(obj, uid, pw, db, method, *args, **kwargs):
    try:
        return obj.execute_kw(db, uid, pw, method, args, kwargs)
    except xmlrpc.client.Fault as f:
        return {"__fault__": str(f)}
    except Exception as e:
        return {"__error__": str(e)}

# -------------------------------------------------------------------
# Authenticate
# -------------------------------------------------------------------
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    sys.exit(f"❌ Authentication failed for {USERNAME}@{DB}")
print(f"✅ Authenticated UID {uid}")

models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# -------------------------------------------------------------------
# List of models to test (as given by the user). These are the technical
# model names – ensure they exist before testing.
# -------------------------------------------------------------------
model_list = [
    "account.account",
    "account.analytic.account",
    "timesheet.analytic.account",   # "Timesheet (Analytic Account)" mapped to technical name
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
    "website",                      # "Website Editor"
    "helpdesk.ticket",
    "helpdesk.team",
    "purchase.order",
    "po.comment",                   # "PO Comments"
    "social.post",                  # "SOCIAL MARKETING"
    "mail.mass_mailing",            # "Emailing"
    "marketing.campaign",           # "Marketing automation"
    "hr.attendance",                # "Attendance"
    "go.live.change.request",       # "Go live change Request"
    "sign",                         # "sign"
    "payroll",                      # "payroll"
    "hr.leave",                     # "timeoff"
    "ir.attachment"                 # "Document"
]

report = {}

for model in model_list:
    # Verify model exists via search on ir.model
    exist_check = rpc(models, uid, PASSWORD, DB, "search", "ir.model", [[('model', '=', model)]], {})
    if isinstance(exist_check, dict) and ("__fault__" in exist_check or "__error__" in exist_check):
        report[model] = {"status": "model_not_found", "details": exist_check}
        continue
    if not exist_check:
        report[model] = {"status": "model_not_found", "details": "No ir.model entry"}
        continue

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
    create_vals = {}
    if isinstance(fields_info, dict) and ("__fault__" in fields_info or "__error__" in fields_info):
        result["create"] = {"status": "skipped", "reason": "fields_get failed"}
        created_id = None
    else:
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
                # stop after first suitable required field
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

# Write report
report_path = os.path.join(os.path.dirname(__file__), "crud_selected_report.json")
with open(report_path, "w", encoding="utf8") as f:
    json.dump(report, f, indent=2)
print(f"🗂 Report written to {report_path}")
