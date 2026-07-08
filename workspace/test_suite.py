import json, os, sys, requests

BASE_URL = 'https://staging-odoo19-captivea.odoo.com'
DB = 'captivea-staging-odoo19-31833465'
USERNAME = 'eva.jessu@captivea.com'
PASSWORD = 'a'

session = requests.Session()

# Authenticate
auth_payload = {
    'jsonrpc': '2.0',
    'method': 'call',
    'params': {
        'db': DB,
        'login': USERNAME,
        'password': PASSWORD,
    }
}
resp = session.post(f'{BASE_URL}/web/session/authenticate', json=auth_payload)
if resp.status_code != 200:
    print('Auth failed')
    sys.exit(1)
uid = resp.json()['result']['uid']

# Helper to call methods
def call(model, method, args=None, kwargs=None):
    args = args or []
    kwargs = kwargs or {}
    payload = {
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {
            'model': model,
            'method': method,
            'args': args,
            'kwargs': kwargs,
        }
    }
    r = session.post(f'{BASE_URL}/web/dataset/call_kw/{model}/{method}', json=payload)
    return r

results = {}

def test_model(model, create_data=None, update_fields=None):
    rec = {'read': None, 'create': None, 'write': None, 'unlink': None}
    # READ (search_read)
    r = call(model, 'search_read', args=[[]], kwargs={'limit': 5})
    if r.status_code == 200 and 'result' in r.json():
        rec['read'] = 'pass'
        ids = r.json()['result']
        sample_ids = [row['id'] for row in ids] if ids else []
    else:
        rec['read'] = f'fail:{r.status_code}'
        sample_ids = []
    # CREATE
    if create_data:
        r = call(model, 'create', args=[create_data])
        if r.status_code == 200 and 'result' in r.json():
            created_id = r.json()['result']
            rec['create'] = 'pass'
        else:
            rec['create'] = f'fail:{r.status_code}'
            created_id = None
    else:
        rec['create'] = 'skipped'
        created_id = None
    # WRITE (update first record if any)
    if update_fields and sample_ids:
        r = call(model, 'write', args=[[sample_ids[0]], update_fields])
        if r.status_code == 200 and r.json().get('result') is True:
            rec['write'] = 'pass'
        else:
            rec['write'] = f'fail:{r.status_code}'
    else:
        rec['write'] = 'skipped'
    # UNLINK (skip deletion to keep records)
    rec['unlink'] = 'skipped'
    return rec

# Define tests per module
modules = {
    'res.partner': { 'create_data': {'name': 'Test Partner', 'email': 'test@example.com'}, 'update_fields': {'email': 'updated@example.com'} },
    'sale.order': { 'create_data': {'partner_id': 2, 'order_line': []}, 'update_fields': {} },
    'project.project': { 'create_data': {'name': 'Test Project'}, 'update_fields': {'name': 'Updated Project'} },
    'hr.timesheet.sheet': { 'create_data': None, 'update_fields': {} },
    'helpdesk.ticket': { 'create_data': {'name': 'Test Ticket'}, 'update_fields': {'name': 'Updated Ticket'} },
    'hr.employee.public': { 'create_data': None, 'update_fields': {} },
    'hr.goal': { 'create_data': None, 'update_fields': {} },
    'attendance.attendance': { 'create_data': None, 'update_fields': {} },
    'hr.recruitment.applicant': { 'create_data': None, 'update_fields': {} },
}

for model, cfg in modules.items():
    results[model] = test_model(model, cfg.get('create_data'), cfg.get('update_fields'))

print(json.dumps(results, indent=2))
