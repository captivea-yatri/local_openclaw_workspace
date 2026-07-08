#!/usr/bin/env python3
import json, sys, xmlrpc.client, urllib.parse

# Credentials (same as before)
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USERNAME = "princy.randimbimanana@captivea.com"
PASSWORD = "a"

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print('Authentication failed')
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)

# Helper functions (same as qa_odoo_full_test)
def add(results, tc, model, action, status, detail=""):
    results.append({"tc": tc, "module": model, "action": action, "status": status, "detail": detail})

def try_read(tc, model, results):
    try:
        ids = models.execute_kw(DB, uid, PASSWORD, model, 'search', [[]], {'limit': 5})
        add(results, tc, model, 'Read', 'PASS', f'Found {len(ids)} records')
        return ids
    except Exception as e:
        add(results, tc, model, 'Read', 'FAIL', str(e))
        return []

def try_write(tc, model, record_id, vals, results):
    try:
        models.execute_kw(DB, uid, PASSWORD, model, 'write', [[record_id], vals])
        add(results, tc, model, 'Write', 'PASS', f'Wrote {vals}')
    except xmlrpc.client.Fault as fault:
        add(results, tc, model, 'Write', 'BLOCKED', f'Permission denied (fault {fault.faultCode})')
    except Exception as e:
        add(results, tc, model, 'Write', 'FAIL', str(e))

def try_create(tc, model, vals, results):
    try:
        rec_id = models.execute_kw(DB, uid, PASSWORD, model, 'create', [vals])
        add(results, tc, model, 'Create', 'PASS', f'Created id={rec_id}')
        return rec_id
    except xmlrpc.client.Fault as fault:
        add(results, tc, model, 'Create', 'FAIL', f'Fault {fault.faultString}')
        return None
    except Exception as e:
        add(results, tc, model, 'Create', 'FAIL', str(e))
        return None

def try_delete(tc, model, rec_id, results):
    add(results, tc, model, 'Delete', 'SKIPPED', f'Skipped deletion of id={rec_id}')

# Generic test similar to qa_odoo_full_test generic_test_model
def generic_test(start_tc, model, results):
    tc = start_tc
    # READ
    ids = try_read(tc, model, results)
    tc += 1
    # Determine fields
    fields = models.execute_kw(DB, uid, PASSWORD, 'ir.model.fields', 'search_read', [[('model', '=', model)]], {'fields': ['name','ttype','required']})
    # WRITE
    writable = None
    for f in fields:
        if f['name'] in ('name','display_name') and f['ttype'] in ('char','text'):
            writable = f['name']
            break
    if ids and writable:
        try_write(tc, model, ids[0], {writable: f'QA edit {model}'}, results)
    else:
        add(results, tc, model, 'Write', 'SKIPPED', 'No writable field or no record')
    tc += 1
    # CREATE / DELETE
    required = {f['name']:f for f in fields if f['required']}
    if any(k in required for k in ('name','code')):
        vals = {}
        if 'name' in required:
            vals['name'] = f'QA {model}'
        if 'code' in required:
            vals['code'] = f'QA_{model.upper()}'
        for fname,finfo in required.items():
            if fname in vals:
                continue
            if finfo['ttype'] == 'char':
                vals[fname] = f'QA_{fname}'
            elif finfo['ttype'] == 'integer':
                vals[fname] = 1
            elif finfo['ttype'] == 'float':
                vals[fname] = 1.0
            elif finfo['ttype'] == 'boolean':
                vals[fname] = True
        rec_id = try_create(tc, model, vals, results)
        if rec_id:
            try_delete(tc+1, model, rec_id, results)
        else:
            add(results, tc+1, model, 'Delete', 'SKIPPED', 'Create failed')
        tc += 2
    else:
        add(results, tc, model, 'Create', 'SKIPPED', 'No obvious required name/code')
        add(results, tc+1, model, 'Delete', 'SKIPPED', 'No record created')
        tc += 2
    return tc

# List of modules requested (including ones already in default list, duplicates are fine)
MODULES = [
    "account.account",
    "account.analytic.account",
    "account.analytic.account",  # Timesheet alias
    "hr.applicant",
    "hr.employee.public",
    "gamification.challenge",
    "gamification.goal",
    "account.journal",
    "account.payment",
    "account.tax",
    "product.template",
    "product.product",
    "project.task",
    "project.project.stage",
    "sale.order.line",
    "crm.stage",
    "crm.lost.reason",
    "product.pricelist",
    "website",
    "helpdesk.team",
    "social.media",
    "hr.attendance",
    "go.live.change.request",
    "hr.leave",
    "documents.document",
]

results = []
next_tc = 1000  # start after existing tests
for mod in MODULES:
    try:
        next_tc = generic_test(next_tc, mod, results)
    except Exception as e:
        add(results, next_tc, mod, 'Generic test', 'FAIL', str(e))
        next_tc += 1

# Human‑readable output
print('=== Selected Modules CRUD Report ===')
print(f'Total cases: {len(results)}')
for rec in results:
    print(f"TC {rec['tc']:4d} | {rec['module']:<30} | {rec['action']:<8} | {rec['status']:<8} | {rec['detail']}")
