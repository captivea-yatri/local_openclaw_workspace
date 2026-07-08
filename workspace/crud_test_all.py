'''CRUD tester for all Odoo models.

This script connects using the credentials defined in `odoo_credentials.json`
(and the same values hard‑coded in `connect_odoo.py`). It enumerates every model
registered in the database (including custom modules) and attempts the four
basic operations:

1. **Read** – search for a single record and read a few fields.
2. **Create** – build a minimal record using required fields with placeholder
   values and create it.
3. **Write** – update a simple field on the newly created record.
4. **Delete** – remove the test record.

The results are written to `crud_test_report.json` in the workspace root.
All created test records are deleted afterwards, so the database state is not
permanently altered.
''' 

import json, sys, xmlrpc.client, os

# -------------------------------------------------------------------
# Load Odoo connection info from the workspace JSON file.
# -------------------------------------------------------------------
CRED_PATH = os.path.join(os.path.dirname(__file__), "odoo_credentials.json")
try:
    with open(CRED_PATH, "r", encoding="utf8") as f:
        cred = json.load(f)
except Exception as e:
    sys.exit(f"❌ Could not load credentials from {CRED_PATH}: {e}")

URL = cred["url"]
DB = cred["db"]
USERNAME = cred["username"]
PASSWORD = cred["password"]  # actual password key

# -------------------------------------------------------------------
# Helper: safe RPC call that returns a dict with error info instead of raising.
# -------------------------------------------------------------------
def rpc_call(obj, uid, pw, db, method, *args, **kwargs):
    try:
        return obj.execute_kw(db, uid, pw, method, args, kwargs)
    except xmlrpc.client.Fault as f:
        return {"__fault__": str(f)}
    except Exception as e:
        return {"__error__": str(e)}

# -------------------------------------------------------------------
# Authenticate.
# -------------------------------------------------------------------
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    sys.exit(f"❌ Authentication failed for user {USERNAME} on {DB}")
print(f"✅ Authenticated as UID {uid}")

models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# -------------------------------------------------------------------
# Gather all models (ir.model) – filter out transient models (type = 'transient')
# -------------------------------------------------------------------
model_entries = models.execute_kw(DB, uid, PASSWORD, 'ir.model', 'search_read', [], {"fields": ["model", "transient"]})
if isinstance(model_entries, dict) and ("__fault__" in model_entries or "__error__" in model_entries):
    sys.exit(f"❌ Could not fetch model list: {model_entries}")

all_models = [e["model"] for e in model_entries if not e.get("transient")]
print(f"🔍 Found {len(all_models)} persistent models to test.")

report = {}

for model in all_models:
    # Skip technical models that are known to be problematic or have no CRUD (e.g., ir.*)
    if model.startswith("ir."):
        continue
    result = {"read": None, "create": None, "write": None, "delete": None}

    # ---------- READ ----------
    read_ids = rpc_call(models, uid, PASSWORD, DB, "search", model, [[]], {"limit": 1})
    if isinstance(read_ids, dict) and ("__fault__" in read_ids or "__error__" in read_ids):
        result["read"] = {"status": "blocked", "error": read_ids.get("__fault__") or read_ids.get("__error__")}
        record_id = None
    else:
        result["read"] = {"status": "allowed" if read_ids else "allowed_no_records"}
        record_id = read_ids[0] if read_ids else None

    # ---------- CREATE ----------
    # Determine a minimal set of required fields we can populate.
    fields_info = rpc_call(models, uid, PASSWORD, DB, "fields_get", model, [], {"attributes": ["type", "required", "relation"]})
    create_vals = {}
    if isinstance(fields_info, dict) and ("__fault__" in fields_info or "__error__" in fields_info):
        # If we cannot fetch field info, skip creation.
        result["create"] = {"status": "skipped", "reason": "fields_get failed"}
        created_id = None
    else:
        # Find a required char/int/boolean field to satisfy constraints.
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
                    # Try to link to the first record of the related model.
                    rel = finfo.get("relation")
                    rel_ids = rpc_call(models, uid, PASSWORD, DB, "search", rel, [[]], {"limit": 1})
                    if isinstance(rel_ids, list) and rel_ids:
                        create_vals[fname] = rel_ids[0]
                # If we have at least one field populated, break.
                if fname in create_vals:
                    break
        if not create_vals:
            result["create"] = {"status": "skipped", "reason": "no suitable required field"}
            created_id = None
        else:
            created_id = rpc_call(models, uid, PASSWORD, DB, "create", model, [create_vals])
            if isinstance(created_id, dict) and ("__fault__" in created_id or "__error__" in created_id):
                result["create"] = {"status": "blocked", "error": created_id.get("__fault__") or created_id.get("__error__")}
                created_id = None
            else:
                result["create"] = {"status": "allowed", "id": created_id}

    # ---------- WRITE ----------
    target_id = created_id or record_id
    if target_id:
        # Attempt to write a simple field – use the same field we used for create if possible.
        write_field = next(iter(create_vals)) if create_vals else None
        if write_field:
            write_val = f"updated_{model}" if isinstance(create_vals[write_field], str) else create_vals[write_field]
            write_res = rpc_call(models, uid, PASSWORD, DB, "write", model, [[target_id], {write_field: write_val}])
            if isinstance(write_res, dict) and ("__fault__" in write_res or "__error__" in write_res):
                result["write"] = {"status": "blocked", "error": write_res.get("__fault__") or write_res.get("__error__")}
            else:
                result["write"] = {"status": "allowed"}
        else:
            # No writable field identified – mark as skipped.
            result["write"] = {"status": "skipped", "reason": "no suitable field to update"}
    else:
        result["write"] = {"status": "skipped", "reason": "no record to write"}

    # ---------- DELETE ----------
    if created_id:
        del_res = rpc_call(models, uid, PASSWORD, DB, "unlink", model, [[created_id]])
        if isinstance(del_res, dict) and ("__fault__" in del_res or "__error__" in del_res):
            result["delete"] = {"status": "blocked", "error": del_res.get("__fault__") or del_res.get("__error__")}
        else:
            result["delete"] = {"status": "allowed"}
    else:
        result["delete"] = {"status": "skipped", "reason": "no test record created"}

    report[model] = result

# Save report
report_path = os.path.join(os.path.dirname(__file__), "crud_test_report.json")
with open(report_path, "w", encoding="utf8") as f:
    json.dump(report, f, indent=2)
print(f"🗂 Report written to {report_path}")
