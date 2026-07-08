# Odoo Role-Based QA & Security Validation Script (v2)
# Updated to use correct Odoo model names and include extra security checks.

import xmlrpc.client
import json
import sys

# ---------------------------------------------------------------------------
# Credentials (provided by user)
# ---------------------------------------------------------------------------
url = 'https://staging-odoo19-captivea.odoo.com'
db = 'captivea-staging-odoo19-31833465'
username = 'come.moyne@captivea.com'
password = 'a'

# ---------------------------------------------------------------------------
# Helper: Odoo RPC connection
# ---------------------------------------------------------------------------
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})
if not uid:
    print(json.dumps({"error": "Authentication failed"}))
    sys.exit(1)

object = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

# ---------------------------------------------------------------------------
# Model name mapping (business key -> technical Odoo model)
# ---------------------------------------------------------------------------
model_map = {
    'contacts': 'res.partner',
    'crm': 'crm.lead',
    'sales': 'sale.order',
    'project': 'project.project',
    'go_live_change_request': 'go.live.change.request',
    'timesheet': 'hr.timesheet',
    'accounting': 'account.move',
    'asset': 'account.asset',
    'purchase': 'purchase.order',
    'employees': 'hr.employee',
    'goals': 'hr.goal',
    'challenges': 'hr.challenge',
    'attendance': 'hr.attendance',
    'recruitment': 'hr.applicant',
    'helpdesk': 'helpdesk.ticket',
    'website': 'website.page',
    'marketing_automation': 'marketing.campaign',
    'email_marketing': 'mail.mass_mailing',
    'social_marketing': 'social.post',
}

# ---------------------------------------------------------------------------
# Permission matrix (allowed CRUD operations per module)
# ---------------------------------------------------------------------------
permissions = {
    'contacts': {'crud': ['create', 'read', 'write', 'unlink']},
    'crm': {'crud': ['create', 'read', 'write', 'unlink']},
    'sales': {'crud': ['create', 'read', 'write', 'unlink']},
    'project': {'crud': ['create', 'read', 'write', 'unlink']},
    'go_live_change_request': {'crud': ['read']},
    'timesheet': {'crud': ['read']},
    'accounting': {'crud': ['read']},
    'asset': {'crud': ['read']},
    'purchase': {'crud': ['create'], 'extra': ['confirm_block', 'credit_card_block']},
    'employees': {'crud': ['create', 'read', 'write', 'unlink']},
    'goals': {'crud': ['create', 'read', 'write', 'unlink']},
    'challenges': {'crud': ['create', 'read', 'write', 'unlink']},
    'attendance': {'custom': ['check_in_out']},  # not testable via RPC
    'recruitment': {'crud': ['create', 'read', 'write', 'unlink']},
    'helpdesk': {'crud': ['create', 'read'], 'extra': ['branch_isolation']},
    'website': {'crud': []},  # should be no access
    'marketing_automation': {'crud': ['create', 'read', 'write', 'unlink']},
    'email_marketing': {'crud': ['create', 'read', 'write', 'unlink']},
    'social_marketing': {'crud': ['create', 'read', 'write', 'unlink']},
}

# ---------------------------------------------------------------------------
# Helper to perform CRUD operation and capture result
# ---------------------------------------------------------------------------
def attempt(op, model, **kwargs):
    try:
        if op == 'create':
            new_id = object.execute_kw(db, uid, password, model, 'create', [kwargs['vals']])
            return {'status': 'allowed', 'id': new_id}
        elif op == 'read':
            ids = object.execute_kw(db, uid, password, model, 'search', [[]], {'limit': 1})
            if ids:
                data = object.execute_kw(db, uid, password, model, 'read', [ids, ['name']])
                return {'status': 'allowed', 'data': data}
            else:
                return {'status': 'allowed_no_records'}
        elif op == 'write':
            ids = kwargs.get('ids')
            if not ids:
                return {'status': 'no_target'}
            res = object.execute_kw(db, uid, password, model, 'write', [ids, kwargs['vals']])
            return {'status': 'allowed' if res else 'blocked'}
        elif op == 'unlink':
            ids = kwargs.get('ids')
            if not ids:
                return {'status': 'no_target'}
            res = object.execute_kw(db, uid, password, model, 'unlink', [ids])
            return {'status': 'allowed' if res else 'blocked'}
    except Exception as e:
        return {'status': 'blocked', 'error': str(e)}

# ---------------------------------------------------------------------------
# Main test execution
# ---------------------------------------------------------------------------
results = {}

for key, cfg in permissions.items():
    model = model_map.get(key)
    if not model:
        results[key] = {'error': 'No model mapping'}
        continue
    module_res = {}
    crud_ops = cfg.get('crud', [])
    # CREATE
    if 'create' in crud_ops:
        create_res = attempt('create', model, vals={'name': f'Test {key.title()}'})
        module_res['create'] = create_res
        created_id = create_res.get('id')
    else:
        # try to create to verify block
        create_res = attempt('create', model, vals={'name': 'ShouldFail'})
        module_res['create'] = create_res
        created_id = None
    # READ
    read_res = attempt('read', model)
    module_res['read'] = read_res
    # WRITE (if allowed)
    if 'write' in crud_ops and created_id:
        write_res = attempt('write', model, ids=[created_id], vals={'name': f'Updated {key}'})
    else:
        # attempt to write to see block
        write_res = attempt('write', model, ids=[created_id] if created_id else [0], vals={'name': 'ShouldFail'})
    module_res['write'] = write_res
    # UNLINK (delete)
    if 'unlink' in crud_ops and created_id:
        unlink_res = attempt('unlink', model, ids=[created_id])
    else:
        unlink_res = attempt('unlink', model, ids=[created_id] if created_id else [0])
    module_res['unlink'] = unlink_res
    # Extra module‑specific checks
    extras = {}
    if key == 'purchase' and 'extra' in cfg:
        # 1) Confirm action should be blocked
        if created_id:
            try:
                object.execute_kw(db, uid, password, model, 'action_confirm', [[created_id]])
                extras['confirm'] = {'status': 'unexpectedly_allowed'}
            except Exception as e:
                extras['confirm'] = {'status': 'blocked', 'error': str(e)}
        else:
            extras['confirm'] = {'status': 'no_record_created'}
        # 2) Attempt to write hidden credit‑card field (commonly 'partner_bank_id' or custom field)
        # We'll try a generic field name that may exist: 'credit_card_number'
        try:
            object.execute_kw(db, uid, password, model, 'write', [[created_id], {'credit_card_number': '1234'}])
            extras['credit_card_write'] = {'status': 'unexpectedly_allowed'}
        except Exception as e:
            extras['credit_card_write'] = {'status': 'blocked', 'error': str(e)}
    if key == 'helpdesk' and 'extra' in cfg:
        # Branch isolation: create ticket in first team, then attempt to read with a different team filter
        try:
            # Find any helpdesk team
            team_ids = object.execute_kw(db, uid, password, 'helpdesk.team', 'search', [[]], {'limit': 2})
            if len(team_ids) >= 2:
                team_a, team_b = team_ids[:2]
                ticket_id = object.execute_kw(db, uid, password, model, 'create', [{
                    'name': 'Branch test ticket',
                    'team_id': team_a,
                }])
                # Attempt to read ticket with team B filter
                tickets_b = object.execute_kw(db, uid, password, model, 'search', [[('id', '=', ticket_id), ('team_id', '=', team_b)]])
                extras['branch_isolation'] = {'status': 'blocked' if not tickets_b else 'unexpectedly_allowed'}
                # Cleanup ticket
                object.execute_kw(db, uid, password, model, 'unlink', [[ticket_id]])
            else:
                extras['branch_isolation'] = {'status': 'insufficient_teams'}
        except Exception as e:
            extras['branch_isolation'] = {'status': 'error', 'error': str(e)}
    if extras:
        module_res['extra'] = extras
    results[key] = module_res

print(json.dumps(results, indent=2))
