import json, urllib.request, datetime, sys

# ------------------------------------------------------------
# CONFIG – change only if your credentials / URL differ
# ------------------------------------------------------------
URL = "https://2865-2402-a00-152-5177-ef5b-e862-e9c0-6530.ngrok-free.app/jsonrpc"
DB  = "odoo19_captivea2"
USER = "admin1"
PWD  = "a"

# ------------------------------------------------------------
# tiny JSON‑RPC helper
# ------------------------------------------------------------
def rpc(service, method, args):
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": 1,
    }
    req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'),
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
    if "error" in resp:
        raise Exception(resp["error"]["message"])
    return resp["result"]

def auth():
    return rpc('common', 'authenticate', [DB, USER, PWD, {}])

def search(model, domain, limit=0):
    args = [domain]
    kwargs = {}
    if limit:
        kwargs['limit'] = limit
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'search', args, kwargs])

def read(model, ids, fields):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'read', [ids, fields]])

def create(model, vals):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, 'create', [vals]])

def call(model, method, ids, *extra):
    return rpc('object', 'execute_kw', [DB, uid, PWD, model, method, [[ids] + list(extra)]])

# ------------------------------------------------------------
# MAIN – build the broken scenario
# ------------------------------------------------------------
uid = auth()
print('✅ Authenticated UID', uid)

# 1️⃣ pick two active users (any two distinct ones)
user_ids = search('res.users', [('active', '=', True)], limit=5)
if len(user_ids) < 2:
    sys.exit('Not enough active users')
user1, user2 = user_ids[0], user_ids[1]
print('👤 Approvers:', user1, user2)

# 2️⃣ get a quality.issue.type (any)
type_ids = search('quality.issue.type', [], limit=1)
if not type_ids:
    sys.exit('No quality.issue.type found')
issue_type_id = type_ids[0]
print('🔧 Issue type id', issue_type_id)

# 3️⃣ get an employee (any)
emp_ids = search('hr.employee', [], limit=1)
emp_id = emp_ids[0]

# 4️⃣ get a project (any)
proj_ids = search('project.project', [], limit=1)
proj_id = proj_ids[0]

# 5️⃣ create quality.issue.log (minimal fields)
log_vals = {
    'logged_date': datetime.date.today().isoformat(),
    'employee_id': emp_id,
    'project_id': proj_id,
    'description': 'Broken‑scenario test (auto‑generated)',
    'quality_issue_type': issue_type_id,
}
log_id = create('quality.issue.log', log_vals)
print('🗂 Created quality.issue.log id', log_id)

# 6️⃣ create approval.request linked to the log, two approvers
approval_vals = {
    'name': f'Approval for log {log_id}',
    'x_studio_quality_issue_log': log_id,
    'approval_user_ids': [(6, 0, [user1, user2])],
    'request_owner_id': uid,
    'request_state': 'new',
    'category_id': 42,
}
approval_id = create('approval.request', approval_vals)
print('✅ Created approval.request id', approval_id)

# 7️⃣ simulate the bug: schedule activity only for the first approver
# Resolve the generic “To‑Do” activity type
todo_type_id = rpc('object', 'execute_kw', [DB, uid, PWD, 'ir.model.data', 'xmlid_to_res_id', ['mail.mail_activity_data_todo', False, False]])
if not todo_type_id:
    sys.exit('Cannot resolve activity type')
# Direct call to the ORM method activity_schedule (expects act_type_id, user_id)
call('quality.issue.log', 'activity_schedule', log_id, todo_type_id, user1)
print('🔧 Bug simulated – activity only for user', user1)

# 8️⃣ fetch activities linked to this log
activity_ids = search('mail.activity', [('res_model', '=', 'quality.issue.log'), ('res_id', '=', log_id)])
activities = read('mail.activity', activity_ids, ['id', 'user_id'])
print('\n📋 Activities now attached to the log:')
for act in activities:
    print(f"   • activity {act['id']} → user {act['user_id'][0]}")

# 9️⃣ which approver missed the activity?
users_with_activity = {act['user_id'][0] for act in activities}
missing = [u for u in (user1, user2) if u not in users_with_activity]

# 10️⃣ final JSON output with all relevant IDs
result = {
    'quality_issue_log_id': log_id,
    'approval_request_id': approval_id,
    'approver_ids': [user1, user2],
    'activity_ids': activity_ids,
    'approvers_missing_activity': missing,
}
print('\n--- 🎯 BROKEN‑SCENARIO RESULT ------------------------------------------------')
print(json.dumps(result, indent=2))
