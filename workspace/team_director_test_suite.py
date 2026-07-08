import json, sys, requests, os

BASE_URL = 'https://staging-odoo19-captivea.odoo.com'
COOKIE_PATH = '/tmp/odoo4_cookie.txt'

session = requests.Session()
# Load cookies from file (simple format: name=value; ...)
if os.path.exists(COOKIE_PATH):
    with open(COOKIE_PATH) as f:
        raw = f.read().strip()
    # The file contains lines like "session_id=...; path=/; HttpOnly"
    # We'll split by ';' and then by '=' for the first pair.
    parts = raw.split(';')
    for part in parts:
        if '=' in part:
            name, value = part.strip().split('=', 1)
            session.cookies.set(name, value, domain='staging-odoo19-captivea.odoo.com')
else:
    print('Cookie file not found')
    sys.exit(1)

# Helper to call a model method via JSON-RPC
def call(model, method, args=None, kwargs=None):
    payload = {
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {
            'model': model,
            'method': method,
            'args': args or [],
            'kwargs': kwargs or {}
        }
    }
    r = session.post(f'{BASE_URL}/web/dataset/call_kw/{model}/{method}', json=payload)
    return r

results = {}

def test_model(model, create_data=None, update_fields=None, read_limit=5):
    # Define safe fields per model to avoid privileged relational fields
    safe_fields_map = {
        'res.partner': ['id', 'name', 'email'],
        'sale.order': ['id', 'name', 'partner_id'],
        'project.project': ['id', 'name'],
        'account.analytic.line': ['id', 'name', 'user_id', 'project_id'],
        'purchase.order': ['id', 'name', 'partner_id'],
        'hr.recruitment.applicant': ['id', 'name', 'partner_id'],
        'helpdesk.ticket': ['id', 'name', 'partner_id'],
        'attendance.attendance': ['id', 'employee_id', 'check_in', 'check_out'],
        'hr.goal': ['id', 'name', 'user_id'],
        'gamification.challenge': ['id', 'name'],
    }
    safe_fields = safe_fields_map.get(model, ['id'])

    rec = {'read': None, 'create': None, 'write': None, 'unlink': None}
    # READ (search_read)
    # READ (search_read) with safe fields to avoid protected relational fields
    r = call(model, 'search_read', args=[[]], kwargs={'limit': read_limit, 'fields': safe_fields})
    if r.status_code == 200 and 'result' in r.json():
        rec['read'] = 'pass'
        ids = [row['id'] for row in r.json()['result']]
    else:
        rec['read'] = f'fail:{r.status_code}'
        ids = []
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
    if update_fields and ids:
        r = call(model, 'write', args=[[ids[0]], update_fields])
        if r.status_code == 200 and r.json().get('result') is True:
            rec['write'] = 'pass'
        else:
            rec['write'] = f'fail:{r.status_code}'
    else:
        rec['write'] = 'skipped'
    # UNLINK (delete created record)
    if created_id:
        r = call(model, 'unlink', args=[[created_id]])
        if r.status_code == 200 and r.json().get('result') is True:
            rec['unlink'] = 'pass'
        else:
            rec['unlink'] = f'fail:{r.status_code}'
    else:
        rec['unlink'] = 'skipped'
    return rec

# Define test scenarios for Team Director role
modules = {
    'res.partner': {'create_data': {'name': 'TD Test Partner', 'email': 'td@example.com'}, 'update_fields': {'email': 'updated@td.com'}},
    'sale.order': {'create_data': None, 'update_fields': {}},  # read‑only via smart button (no create)
    'project.project': {'create_data': {'name': 'TD Test Project'}, 'update_fields': {'name': 'TD Updated Project'}},
    'account.analytic.line': {'create_data': None, 'update_fields': {}},  # timesheet lines
    'purchase.order': {'create_data': {'partner_id': 2, 'order_line': []}, 'update_fields': {}},
    'hr.recruitment.applicant': {'create_data': None, 'update_fields': {}},
    'helpdesk.ticket': {'create_data': {'name': 'TD Test Ticket'}, 'update_fields': {'name': 'TD Updated Ticket'}},
    'attendance.attendance': {'create_data': None, 'update_fields': {}},
    'hr.goal': {'create_data': None, 'update_fields': {}},
    'gamification.challenge': {'create_data': None, 'update_fields': {}},
}

for model, cfg in modules.items():
    results[model] = test_model(model, cfg.get('create_data'), cfg.get('update_fields'))

print(json.dumps(results, indent=2))
