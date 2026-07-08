# --------------------------------------------------------------
# role_based_audit.py
# --------------------------------------------------------------
# A generic Odoo role‑based QA & security auditor.
#
# Usage (from workspace root):
#   python3 role_based_audit.py \
#       --url https://staging-odoo19-captivea.odoo.com \
#       --db captivea-staging-odoo19-31833465 \
#       --user <login> \
#       --pw <password> \
#       --role "<ROLE_NAME>" \
#       --matrix ./role_matrix_42.json
#
# The script will:
#   1. Load the role‑access matrix (JSON format – see example below).
#   2. Derive a CRUD policy for every Odoo model that appears in the matrix.
#   3. Authenticate to Odoo via XML‑RPC.
#   4. Run the same probe logic as odoo_autonomous_audit_v2.py,
#      but now it can **compare expected vs. actual** results.
#   5. Emit a nicely formatted HTML report + a raw JSON dump.
#
# Dependencies: built‑in libs only (xmlrpc, json, argparse, jinja2 optional
#               – if Jinja2 is missing the script falls back to plain HTML).
# --------------------------------------------------------------

import argparse, json, sys, xmlrpc.client, os, datetime, traceback
from collections import defaultdict

# -----------------------------------------------------------------
# Helper – safe RPC wrapper (returns dict with __fault__/__error when needed)
# -----------------------------------------------------------------
def rpc_proxy(obj, uid, pw, db):
    def call(method, *args, **kwargs):
        try:
            return obj.execute_kw(db, uid, pw, *args, **kwargs)
        except xmlrpc.client.Fault as f:
            return {"__fault__": str(f)}
        except Exception as e:
            return {"__error__": str(e)}
    return call

# -----------------------------------------------------------------
# Load role matrix file (JSON). Expected shape:
# {
#   "User1": {
#       "Contacts":   { "Access": "Admin",   "CRUD": ["C","R","U","D"] },
#       "CRM":        { "Access": "Read",    "CRUD": ["R"] },
#       ...
#   },
#   "User2": { … },
#   ...
# }
# -----------------------------------------------------------------
def load_matrix(path):
    try:
        with open(path, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception as e:
        sys.exit(f"❌ Could not load role matrix: {e}")

# -----------------------------------------------------------------
# Build a per‑model CRUD expectation dict from the matrix entry.
# We map the human‑readable module names to Odoo model names
# using a tiny lookup table (you can extend it as needed).
# -----------------------------------------------------------------
MODULE_TO_MODEL = {
    # Canonical names (used by the original script)
    "Contacts": "res.partner",
    "CRM": "crm.lead",
    "Sales": "sale.order",
    "Project": "project.project",
    "Go Live Change Request": "go.live.change.request",
    "Timesheet": "hr.timesheet",
    "Accounting": "account.move",
    "Asset": "account.asset",
    "Purchase": "purchase.order",
    "Employee": "hr.employee",
    "Goal": "hr.goal",
    "Challenge": "hr.challenge",
    "Attendance": "hr.attendance",
    "Recruitment": "hr.applicant",
    "Helpdesk": "helpdesk.ticket",
    "Website": "website.page",
    "Marketing Automation": "marketing.campaign",
    "Email Marketing": "mail.mass_mailing",
    "Social Marketing": "social.post",
    # Legacy aliases that appear in the provided matrix
    "Contact": "res.partner",
    "Go Live Change Request": "go.live.change.request",
    "Accounting": "account.move",
    "Asset": "account.asset",
    "Purchase": "purchase.order",
    "Employee": "hr.employee",
    "Goal": "hr.goal",
    "Challenge": "hr.challenge",
    "Attendance": "hr.attendance",
    "Recruitment": "hr.applicant",
    "Helpdesk": "helpdesk.ticket",
    "Website": "website.page",
    "Marketing Automation": "marketing.campaign",
    "Email Marketing": "mail.mass_mailing",
    "Social Marketing": "social.post",
}
# CRUD shortcut → meaning
CRUD_MAP = {
    "C": "create",
    "R": "read",
    "U": "write",
    "D": "unlink",
}

def build_expected_policy(role_entry):
    """Return dict: model → {operation: expected_status ('allowed'/'blocked') }"""
    policy = defaultdict(dict)
    for human_mod, spec in role_entry.items():
        model = MODULE_TO_MODEL.get(human_mod)
        if not model:
            continue  # unknown module – skip
        crud = spec.get("CRUD", [])
        # default = blocked, then mark allowed per list
        for op in ["create", "read", "write", "unlink"]:
            policy[model][op] = "blocked"
        for letter in crud:
            op = CRUD_MAP.get(letter.upper())
            if op:
                policy[model][op] = "allowed"
        # Handle hybrid‑specific overrides (e.g. Journals / Taxes read‑only)
        if spec.get("Hybrid"):
            for sub, mode in spec["Hybrid"].items():
                key = f"{model}.{sub}"
                policy[key] = {"read": "allowed", "write": "blocked", "create": "blocked", "unlink": "blocked"}
    return policy

# -----------------------------------------------------------------
# Core test for a single model – returns actual CRUD results dict.
# -----------------------------------------------------------------
def test_model(rpc, model):
    result = {"model": model, "crud": {}, "extra": {}}
    # ---------- READ ----------
    read_ids = rpc("search", model, [[]], {"limit": 1})
    if isinstance(read_ids, dict) and ("__fault__" in read_ids or "__error__" in read_ids):
        result["crud"]["read"] = {"status": "blocked", "error": read_ids.get("__fault__") or read_ids.get("__error__")}
        ids = []
    else:
        result["crud"]["read"] = {"status": "allowed" if read_ids else "allowed_no_records"}
        ids = read_ids

    # ---------- CREATE ----------
    fields = rpc("fields_get", model, [], {"attributes": ["type", "required"]})
    if isinstance(fields, dict) and ("__fault__" in fields or "__error__" in fields):
        create_vals = {"name": f"Test {model}"}
    else:
        req_char = None
        for fname, finfo in fields.items():
            if finfo.get("required") and finfo.get("type") == "char":
                req_char = fname
                break
        if not req_char and "name" in fields:
            req_char = "name"
        create_vals = {req_char: f"Test {model}"} if req_char else {"name": f"Test {model}"}
    create_res = rpc("create", model, [create_vals])
    if isinstance(create_res, dict) and ("__fault__" in create_res or "__error__" in create_res):
        result["crud"]["create"] = {"status": "blocked", "error": create_res.get("__fault__") or create_res.get("__error__")}
        new_id = None
    else:
        result["crud"]["create"] = {"status": "allowed", "id": create_res}
        new_id = create_res

    # ---------- WRITE ----------
    target_id = new_id or (ids[0] if ids else None)
    if target_id:
        write_res = rpc("write", model, [[target_id], {"name": f"Updated {model}"}])
        if isinstance(write_res, dict) and ("__fault__" in write_res or "__error__" in write_res):
            result["crud"]["write"] = {"status": "blocked", "error": write_res.get("__fault__") or write_res.get("__error__")}
        else:
            result["crud"]["write"] = {"status": "allowed"}
    else:
        result["crud"]["write"] = {"status": "blocked", "error": "no record to write"}

    # ---------- DELETE ----------
    if new_id:
        del_res = rpc("unlink", model, [[new_id]])
        if isinstance(del_res, dict) and ("__fault__" in del_res or "__error__" in del_res):
            result["crud"]["unlink"] = {"status": "blocked", "error": del_res.get("__fault__") or del_res.get("__error__")}
        else:
            result["crud"]["unlink"] = {"status": "allowed"}
    else:
        del_res = rpc("unlink", model, [[target_id]]) if target_id else {"__fault__": "no target"}
        if isinstance(del_res, dict) and ("__fault__" in del_res or "__error__" in del_res):
            result["crud"]["unlink"] = {"status": "blocked", "error": del_res.get("__fault__") or del_res.get("__error__")}
        else:
            result["crud"]["unlink"] = {"status": "allowed"}

    # ---------- EXPORT (optional) ----------
    if ids:
        try:
            rpc("export_data", model, [ids, ["name"]])
            result["extra"]["export"] = {"status": "allowed"}
        except Exception as e:
            result["extra"]["export"] = {"status": "blocked", "error": str(e)}
    else:
        result["extra"]["export"] = {"status": "no_records"}

    return result

# -----------------------------------------------------------------
# Compare actual vs. expected for one model
# -----------------------------------------------------------------
def compare(policy, actual):
    mismatches = []
    for op, expected in policy.items():
        actual_res = actual["crud"].get(op, {})
        actual_status = actual_res.get("status")
        if expected == "allowed" and actual_status != "allowed":
            mismatches.append({"op": op, "expected": "allowed", "got": actual_status, "detail": actual_res.get("error")})
        if expected == "blocked" and actual_status == "allowed":
            mismatches.append({"op": op, "expected": "blocked", "got": "allowed", "detail": None})
    return mismatches

# -----------------------------------------------------------------
# HTML report rendering (very light – uses f‑strings, no external templating)
# -----------------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"UTF-8\"><title>Odoo Role‑Audit – {role}</title>
<style>
body {{font-family:Arial,sans-serif; margin:1rem;}}
h1 {{color:#2c3e50;}}
table {{border-collapse:collapse; width:100%; margin-top:0.5rem;}}
th,td {{border:1px solid #bbb; padding:0.4rem; text-align:left;}}
th {{background:#ecf0f1;}}
.pass {{color:#27ae60; font-weight:bold;}}
.fail {{color:#c0392b; font-weight:bold;}}
</style></head><body>
<h1>Odoo Role‑Based QA / Security Audit</h1>
<p><strong>Role:</strong> {role}<br>
<strong>User:</strong> {user}<br>
<strong>Timestamp:</strong> {ts}</p>

<h2>Executive Summary</h2>
<ul>
<li>Total checks executed: {total}</li>
<li>Passed: {passed}</li>
<li>Failed / Mismatched: {failed}</li>
<li>Critical gaps (expected allowed but blocked): {critical}</li>
</ul>

<h2>Per‑module details</h2>
{module_tables}
</body></html>
"""

def render_module_table(model, actual, mism):
    rows = ""
    for op in ["create","read","write","unlink"]:
        status = actual["crud"].get(op, {}).get("status", "N/A")
        cls = "pass" if status == "allowed" else "fail"
        rows += f"<tr><td>{op}</td><td class='{cls}'>{status}</td></tr>"
    exp_status = actual["extra"].get("export", {}).get("status", "N/A")
    rows += f"<tr><td>export</td><td class='{'pass' if exp_status=='allowed' else 'fail'}'>{exp_status}</td></tr>"
    mismatch_html = "<em>None</em>" if not mism else "<ul>" + "".join(f"<li>{m['op'].upper()}: expected {m['expected']}, got {m['got']}</li>" for m in mism) + "</ul>"
    return f"<h3>{model}</h3><table><thead><tr><th>Operation</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table><p><strong>Mismatches:</strong> {mismatch_html}</p>"

# -----------------------------------------------------------------
# Main driver
# -----------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Role‑based Odoo QA & Security Auditor")
    parser.add_argument("--url", required=True, help="Odoo instance URL")
    parser.add_argument("--db", required=True, help="Database name")
    parser.add_argument("--user", required=True, help="Login email")
    parser.add_argument("--pw", required=True, help="Password")
    parser.add_argument("--role", required=True, help="Role name as appears in the matrix JSON")
    parser.add_argument("--matrix", required=True, help="Path to role‑matrix JSON file")
    parser.add_argument("--out", default="role_audit_report", help="Base name for output files")
    args = parser.parse_args()

    matrix = load_matrix(args.matrix)
    if args.role not in matrix:
        sys.exit(f"❌ Role '{args.role}' not found in matrix")
    role_policy = build_expected_policy(matrix[args.role])

    common = xmlrpc.client.ServerProxy(f"{args.url}/xmlrpc/2/common")
    uid = common.authenticate(args.db, args.user, args.pw, {})
    if not uid:
        sys.exit("❌ Authentication failed")
    obj = xmlrpc.client.ServerProxy(f"{args.url}/xmlrpc/2/object")
    rpc = rpc_proxy(obj, uid, args.pw, args.db)

    results = {}
    mismatches_by_model = {}
    total_checks = passed = failed = critical = 0

    for model, expected_ops in role_policy.items():
        if "." in model:
            continue
        actual = test_model(rpc, model)
        results[model] = actual
        mism = compare(expected_ops, actual)
        mismatches_by_model[model] = mism
        for op, exp in expected_ops.items():
            total_checks += 1
            act_status = actual["crud"].get(op, {}).get("status")
            if exp == "allowed" and act_status == "allowed":
                passed += 1
            elif exp == "allowed" and act_status != "allowed":
                failed += 1
                critical += 1
            elif exp == "blocked" and act_status == "blocked":
                passed += 1
            else:
                failed += 1

    module_tables = "".join(render_module_table(m, results[m], mismatches_by_model[m]) for m in results)
    html = HTML_TEMPLATE.format(
        role=args.role,
        user=args.user,
        ts=datetime.datetime.utcnow().isoformat() + "Z",
        total=total_checks,
        passed=passed,
        failed=failed,
        critical=critical,
        module_tables=module_tables,
    )
    html_path = f"{args.out}_{args.role.replace(' ', '_')}.html"
    json_path = f"{args.out}_{args.role.replace(' ', '_')}.json"
    with open(html_path, "w", encoding="utf8") as f:
        f.write(html)
    with open(json_path, "w", encoding="utf8") as f:
        json.dump({"role": args.role, "user": args.user, "results": results, "mismatches": mismatches_by_model}, f, indent=2)
    print(f"\n✅ Report generated:\n  • HTML → {html_path}\n  • JSON → {json_path}")
    print(f"\nSummary → Total:{total_checks}  Passed:{passed}  Failed:{failed}  Critical gaps:{critical}")

if __name__ == "__main__":
    main()
