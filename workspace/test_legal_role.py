"""
Legal Role Comprehensive QA + Security Validation for Odoo ERP
Runs a series of XML-RPC checks against the staging Odoo instance using the provided RBAC test credentials.
Generates a JSON report matching the required output format.
"""

import json, sys, traceback
from urllib.parse import urlparse
import xmlrpc.client

# Load credentials
with open('odoo_rbac_credentials.json') as f:
    creds = json.load(f)

url = creds['url']
dbname = creds['database']
username = creds['username']
password = creds['password']

parsed = urlparse(url)
host = parsed.hostname
port = parsed.port or (443 if parsed.scheme == 'https' else 80)
use_ssl = parsed.scheme == 'https'
protocol = 'https' if use_ssl else 'http'
common_url = f"{protocol}://{host}:{port}/xmlrpc/2/common"
object_url = f"{protocol}://{host}:{port}/xmlrpc/2/object"

common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(dbname, username, password, {})
if not uid:
    print(json.dumps({"error": "Authentication failed"}))
    sys.exit(1)

objects = xmlrpc.client.ServerProxy(object_url)

# Helper to perform an XML-RPC call and capture permission errors
def call(method, *args, **kwargs):
    try:
        return getattr(objects, method)(*args, **kwargs), None
    except xmlrpc.client.Fault as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)

# Define modules and expected permissions (read/write/create/delete)
modules = {
    'res.partner': {'read': True, 'write': False, 'create': False, 'delete': False},
    'sale.order': {'read': True, 'write': False, 'create': False, 'delete': False},
    'project.project': {'read': True, 'write': False, 'create': False, 'delete': False},
    'account.move': {'read': True, 'write': False, 'create': False, 'delete': False},
    'account.asset': {'read': True, 'write': False, 'create': False, 'delete': False},
    'hr.timesheet.sheet': {'read': True, 'write': False, 'create': False, 'delete': False},
    'helpdesk.ticket': {'read': True, 'write': False, 'create': True, 'delete': False},
    'attendance.attendance': {'read': True, 'write': True, 'create': True, 'delete': False},
    'hr.recruitment.stage': {'read': False, 'write': False, 'create': False, 'delete': False},
    'crm.lead': {'read': False, 'write': False, 'create': False, 'delete': False},
    'purchase.order': {'read': False, 'write': False, 'create': False, 'delete': False},
}

report = {
    "executed_tests": 0,
    "module_results": {},
    "critical_failures": []
}

for model, perms in modules.items():
    res = {
        "read": None,
        "write": None,
        "create": None,
        "delete": None,
        "violations": []
    }
    # READ test: search_read limited to 1 record
    data, err = call('execute_kw', dbname, uid, password, model, 'search_read', [[]], {'limit': 1})
    if err:
        if perms['read']:
            res['read'] = "failed"
            res['violations'].append('Read access denied')
        else:
            res['read'] = "blocked"
    else:
        res['read'] = "allowed" if perms['read'] else "unexpected"
        if not perms['read']:
            res['violations'].append('Read access unexpectedly allowed')
    # CREATE test (if allowed)
    create_id = None
    if perms['create']:
        dummy = {}
        try:
            create_id = objects.execute_kw(dbname, uid, password, model, 'create', [dummy])
            res['create'] = "allowed"
        except xmlrpc.client.Fault as e:
            res['create'] = "failed"
            res['violations'].append('Create blocked despite expected permission')
    else:
        # attempt create to ensure blocked
        dummy = {}
        try:
            objects.execute_kw(dbname, uid, password, model, 'create', [dummy])
            res['create'] = "unexpected"
            res['violations'].append('Create unexpectedly allowed')
        except Exception:
            res['create'] = "blocked"
    # WRITE test (if allowed and we have a record)
    if perms['write'] and (res['read'] == "allowed" or res['read'] == "unexpected"):
        # use the first read record id if available
        record_id = None
        if data:
            record_id = data[0].get('id')
        if record_id:
            try:
                objects.execute_kw(dbname, uid, password, model, 'write', [[record_id], {'name': 'test'}])
                res['write'] = "allowed"
            except Exception:
                res['write'] = "failed"
                res['violations'].append('Write blocked despite expected permission')
        else:
            res['write'] = "n/a"
    else:
        # attempt write to ensure blocked
        record_id = data[0]['id'] if data else None
        if record_id:
            try:
                objects.execute_kw(dbname, uid, password, model, 'write', [[record_id], {'name': 'test'}])
                res['write'] = "unexpected"
                res['violations'].append('Write unexpectedly allowed')
            except Exception:
                res['write'] = "blocked"
        else:
            res['write'] = "n/a"
    # DELETE test (if allowed)
    if perms['delete'] and create_id:
        try:
            objects.execute_kw(dbname, uid, password, model, 'unlink', [[create_id]])
            res['delete'] = "allowed"
        except Exception:
            res['delete'] = "failed"
            res['violations'].append('Delete blocked despite expected permission')
    else:
        # attempt delete of a known record to ensure blocked
        record_id = data[0]['id'] if data else None
        if record_id:
            try:
                objects.execute_kw(dbname, uid, password, model, 'unlink', [[record_id]])
                res['delete'] = "unexpected"
                res['violations'].append('Delete unexpectedly allowed')
            except Exception:
                res['delete'] = "blocked"
        else:
            res['delete'] = "n/a"

    report['module_results'][model] = res
    report['executed_tests'] += 1

# Critical failure detection based on specific modules
critical_conditions = [
    ('crm.lead', 'read'),
    ('purchase.order', 'read'),
    ('hr.recruitment.stage', 'read'),
    ('sale.order', 'write'),
    ('account.move', 'write'),
    ('hr.employee.public', 'write'),
    ('helpdesk.ticket', 'read'),
]
for model, op in critical_conditions:
    result = report['module_results'].get(model, {})
    if result:
        status = result.get(op)
        if status in ('allowed', 'unexpected'):
            report['critical_failures'].append(f"Critical: {model} {op} access {status}")

print(json.dumps(report, indent=2))
