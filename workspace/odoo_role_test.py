# Odoo Role-Based Testing Script
# Auto-generated for Marketing Director & Sales Manager role validation

import xmlrpc.client
import json
import sys

# Credentials (provided by user)
url = 'https://staging-odoo19-captivea.odoo.com'
db = 'captivea-staging-odoo19-31833465'
username = 'fisina.koloina@captivea.com'
password = 'a'

# Helper to call Odoo RPC
common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
uid = common.authenticate(db, username, password, {})
if not uid:
    print('Authentication failed')
    sys.exit(1)

object = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Define role permissions matrix (simplified)
permissions = {
    'contacts': {'admin': ['create', 'read', 'write', 'unlink'], 'no_config': True},
    'crm': {'admin': ['create', 'read', 'write', 'unlink'], 'no_config': True},
    'sales': {'admin': ['create', 'read', 'write', 'unlink'], 'no_config': False},
    'project': {'admin': ['create', 'read', 'write', 'unlink'], 'no_config': True},
    'go_live_change_request': {'read': ['read']},
    'timesheet': {'read': ['read']},
    'accounting': {'read': ['read']},
    'asset': {'read': ['read']},
    'purchase': {'create': ['create'], 'no_confirm': True, 'no_approve': True, 'hide_cc': True},
    'employees': {'admin': ['create', 'read', 'write', 'unlink'], 'no_config': True},
    'goals': {'admin': ['create', 'read', 'write', 'unlink']},
    'challenges': {'admin': ['create', 'read', 'write', 'unlink']},
    'attendance': {'user': ['check_in', 'check_out']},
    'recruitment': {'admin': ['create', 'read', 'write', 'unlink']},
    'helpdesk': {'custom': {'create': True, 'read_branch': True}},
    'website': {'none': []},
    'marketing_automation': {'admin': ['create', 'read', 'write', 'unlink']},
    'email_marketing': {'admin': ['create', 'read', 'write', 'unlink']},
    'social_marketing': {'admin': ['create', 'read', 'write', 'unlink']},
}

# Result collection
results = {}

def test_crud(model, allowed_ops):
    # Attempt each operation and record success/failure
    ops = {}
    # Create
    if 'create' in allowed_ops:
        try:
            # Minimal fields required for creation (depends on model). Using generic placeholder.
            vals = {'name': 'Test Record'}
            new_id = object.execute_kw(db, uid, password, model, 'create', [vals])
            ops['create'] = 'allowed'
        except Exception as e:
            ops['create'] = f'blocked ({e})'
    else:
        try:
            object.execute_kw(db, uid, password, model, 'create', [{'name': 'ShouldFail'}])
            ops['create'] = 'unexpectedly_allowed'
        except Exception as e:
            ops['create'] = 'blocked'
    # Read
    if 'read' in allowed_ops:
        try:
            ids = object.execute_kw(db, uid, password, model, 'search', [[]], {'limit': 1})
            if ids:
                data = object.execute_kw(db, uid, password, model, 'read', [ids, ['name']])
                ops['read'] = 'allowed'
            else:
                ops['read'] = 'allowed_no_records'
        except Exception as e:
            ops['read'] = f'blocked ({e})'
    else:
        try:
            object.execute_kw(db, uid, password, model, 'search', [[]])
            ops['read'] = 'unexpectedly_allowed'
        except Exception as e:
            ops['read'] = 'blocked'
    # Write
    if 'write' in allowed_ops:
        try:
            if ids:
                object.execute_kw(db, uid, password, model, 'write', [ids, {'name': 'Updated Test'}])
                ops['write'] = 'allowed'
            else:
                ops['write'] = 'no_target'
        except Exception as e:
            ops['write'] = f'blocked ({e})'
    else:
        try:
            if ids:
                object.execute_kw(db, uid, password, model, 'write', [ids, {'name': 'ShouldFail'}])
                ops['write'] = 'unexpectedly_allowed'
            else:
                ops['write'] = 'no_target'
        except Exception as e:
            ops['write'] = 'blocked'
    # Unlink (delete)
    if 'unlink' in allowed_ops:
        try:
            if ids:
                object.execute_kw(db, uid, password, model, 'unlink', [ids])
                ops['unlink'] = 'allowed'
            else:
                ops['unlink'] = 'no_target'
        except Exception as e:
            ops['unlink'] = f'blocked ({e})'
    else:
        try:
            if ids:
                object.execute_kw(db, uid, password, model, 'unlink', [ids])
                ops['unlink'] = 'unexpectedly_allowed'
            else:
                ops['unlink'] = 'no_target'
        except Exception as e:
            ops['unlink'] = 'blocked'
    return ops

# Iterate over defined modules
for mod_key, cfg in permissions.items():
    model_name = mod_key.replace('_', '.')  # naive mapping, may need adjustment
    allowed = []
    # Determine allowed ops based on config keys
    for op in ['create', 'read', 'write', 'unlink']:
        if op in cfg:
            allowed.extend(cfg[op])
        elif any(k.startswith(op) for k in cfg):
            # if specific flag like 'no_confirm' doesn't affect CRUD
            continue
    # Test CRUD
    crud_res = test_crud(model_name, allowed)
    results[mod_key] = {'crud': crud_res}

# Print JSON report
print(json.dumps(results, indent=2))
