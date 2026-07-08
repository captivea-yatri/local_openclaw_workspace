import json, urllib.request, sys, datetime

# ---------- Configuration ----------
URL = "https://2865-2402-a00-152-5177-ef5b-e862-e9c0-6530.ngrok-free.app/jsonrpc"
DB = "odoo19_captivea2"
USER = "admin1"
PWD = "a"

def rpc(service, method, args, uid=None, password=PWD):
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": 1,
    }
    req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
    if 'error' in resp:
        raise Exception(resp['error']['message'])
    return resp['result']

def authenticate():
    uid = rpc('common', 'authenticate', [DB, USER, PWD, {}])
    return uid

def search(model, domain, limit=0, order=None):
    args = [domain]
    kwargs = {}
    if limit:
        kwargs['limit'] = limit
    if order:
        kwargs['order'] = order
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'search', [domain], kwargs])

def read(model, ids, fields):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'read', [ids, fields]])

def create(model, vals):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'create', [vals]])

def call(model, method, ids, *extra_args):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, method, [ids] + list(extra_args)])

uid = authenticate()
print('Authenticated uid', uid)

# 1. Get two distinct active users (skip admin if possible)
user_ids = search('res.users', [('active', '=', True)], limit=5)
# Ensure we have at least 2 non‑admin users; admin is likely id=2.
# We'll just take the first two distinct IDs.
if len(user_ids) < 2:
    sys.exit('Not enough users to simulate')
user1, user2 = user_ids[0], user_ids[1]
print('Using users', user1, user2)

# 2. Find a quality.issue.type (any)
issue_type_ids = search('quality.issue.type', [], limit=1)
if not issue_type_ids:
    sys.exit('No quality.issue.type found')
issue_type_id = issue_type_ids[0]
print('Issue type id', issue_type_id)

# 3. Find an employee (any) – we will use the employee that matches user1 if possible
emp_ids = search('hr.employee', [], limit=1)
emp_id = emp_ids[0]
print('Employee id', emp_id)

# 4. Find a project (any)
proj_ids = search('project.project', [], limit=1)
proj_id = proj_ids[0]
print('Project id', proj_id)

# 5. Create a quality.issue.log record (minimal fields)
log_vals = {
    'logged_date': datetime.date.today().isoformat(),
    'employee_id': emp_id,
    'project_id': proj_id,
    'description': 'Broken‑scenario test',
    'quality_issue_type': issue_type_id,
}
log_id = create('quality.issue.log', log_vals)
print('Created quality.issue.log id', log_id)

# 6. Create an approval.request linked to the quality issue log with two approvers.
# Field linking to the log is assumed to be 'x_studio_quality_issue_log' (as used in the test).
# Approvers field on approval.request is 'approval_user_ids' (standard many2many).
approval_vals = {
    'name': 'Test Approval for log %s' % log_id,
    'x_studio_quality_issue_log': log_id,
    'approval_user_ids': [(6, 0, [user1, user2])],
    'request_owner_id': uid,
    'request_state': 'new',
    # required fields may vary; add a minimal generic state.
}
approval_id = create('approval.request', approval_vals)
print('Created approval.request id', approval_id)

# 7. Simulate the broken workflow: create an activity only for the first approver.
activity_type_id = rpc('object', 'execute_kw', [DB, uid, PWD, 'ir.model.data', 'xmlid_to_res_id', ['mail.mail_activity_data_todo']])
# activity_schedule on the quality log will create a mail.activity linked to the log.
# We'll call it manually for user1 only.
call('quality.issue.log', 'activity_schedule', [log_id], activity_type_id, user1)
print('Created activity for user1 only')

# 8. Inspect mail.activity records for this log.
activity_ids = search('mail.activity', [('res_id', '=', log_id), ('res_model', '=', 'quality.issue.log')])
activities = read('mail.activity', activity_ids, ['id', 'user_id'])
print('Activities found:', activities)

# Identify which approver did NOT receive an activity.
users_with_activity = {act['user_id'][0] for act in activities}
missing = [uid for uid in [user1, user2] if uid not in users_with_activity]
print('Approvers without activity:', missing)

# Output the IDs of the broken scenario (keep the records in the DB).
result = {
    'quality_issue_log_id': log_id,
    'approval_request_id': approval_id,
    'approver_ids': [user1, user2],
    'activity_ids': activity_ids,
    'approvers_missing_activity': missing,
}
print('\n--- RESULT ---')
print(json.dumps(result, indent=2))
