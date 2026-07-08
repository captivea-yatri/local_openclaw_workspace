import xmlrpc.client
import json
import sys
import datetime

# Configuration (provided by user)
ODOO_URL = 'https://staging-odoo19-captivea.odoo.com'
DB = 'captivea-staging-odoo19-31833465'
USERNAME = 'sebastien.riss@captivea.com'
PASSWORD = 'a'

# Authenticate
common = xmlrpc.client.ServerProxy(f'{ODOO_URL.rstrip('/')}/xmlrpc/2/common')
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({'error': 'Authentication failed'}))
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f'{ODOO_URL.rstrip('/')}/xmlrpc/2/object')

def call(model, method, *args, **kwargs):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args, kwargs)

# ------------------------------------------------------------------
# Load role matrix for the "Administrative" role
# ------------------------------------------------------------------
with open('role_matrix_by_role.json') as f:
    role_matrix = json.load(f)
role_entry = role_matrix.get('Administrative', {})

# Human‑module → Odoo model mapping (same as role_based_audit.py)
MODULE_TO_MODEL = {
    "Contact": "res.partner",
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
}

# Helper to find a writable "name"‑like field for create/update
def get_name_field(model):
    try:
        fields = call(model, 'fields_get', [], {'attributes': ['type', 'required']})
    except Exception:
        return None
    for fname, finfo in fields.items():
        if finfo.get('required') and finfo.get('type') == 'char':
            return fname
    return 'name' if 'name' in fields else None

# ------------------------------------------------------------------
# Reporting container
# ------------------------------------------------------------------
report = {
    'executive_summary': {},
    'module_results': {},
    'final_verdict': 'UNKNOWN',
}

def record(module, test, passed, details=''):
    report.setdefault('module_results', {}).setdefault(module, []).append({
        'test': test,
        'passed': passed,
        'details': details,
    })

# ------------------------------------------------------------------
# 1️⃣ UI Layer sanity check (menus vs expected modules)
# ------------------------------------------------------------------
try:
    menus = call('ir.ui.menu', 'search_read', [], ['name', 'id'])
    visible = set()
    for m in menus:
        n = m['name'].lower()
        if 'crm' in n:
            visible.add('CRM')
        if 'website' in n:
            visible.add('Website')
        if 'helpdesk' in n:
            visible.add('Helpdesk')
        if 'hr' in n or 'employees' in n:
            visible.add('Employees')
        if 'goal' in n:
            visible.add('Goals')
        if 'attendance' in n:
            visible.add('Attendance')
        if 'purchase' in n:
            visible.add('Purchase')
    expected = set(role_entry.keys())
    missing = expected - visible
    extra = visible - expected
    record('UI Layer', 'Module visibility', not missing, f'Missing: {missing}, Extra: {extra}')
except Exception as e:
    record('UI Layer', 'Module visibility', False, str(e))

# ------------------------------------------------------------------
# 2️⃣ Matrix‑driven CRUD tests per module
# ------------------------------------------------------------------
for human_mod, spec in role_entry.items():
    model = MODULE_TO_MODEL.get(human_mod)
    if not model:
        continue  # unmapped module – skip
    crud = spec.get('CRUD', [])

    # ----- READ -----
    try:
        ids = call(model, 'search', [], {'limit': 1})
        read_allowed = True
    except Exception:
        read_allowed = False
    expected = 'R' in crud
    record(human_mod, 'Read', (read_allowed == expected), f'Allowed={read_allowed}, Expected={expected}')

    # ----- CREATE -----
    name_field = get_name_field(model)
    if name_field:
        try:
            cid = call(model, 'create', {name_field: f'QaTest {human_mod}'})
            created = True
        except Exception:
            created = False
        expected = 'C' in crud
        record(human_mod, 'Create', (created == expected), f'Created={created}, Expected={expected}')
    else:
        expected = 'C' in crud
        record(human_mod, 'Create', not expected, 'No suitable field to create; expected create=False')
        created = False
        cid = None

    # ----- UPDATE -----
    target_id = None
    if created and cid:
        target_id = cid
    else:
        try:
            existing = call(model, 'search', [], {'limit': 1})
            if existing:
                target_id = existing[0]
        except Exception:
            pass
    if target_id and name_field:
        try:
            call(model, 'write', [target_id], {name_field: f'QaUpdated {human_mod}'})
            updated = True
        except Exception:
            updated = False
        expected = 'U' in crud
        record(human_mod, 'Update', (updated == expected), f'Updated={updated}, Expected={expected}')
    else:
        expected = 'U' in crud
        record(human_mod, 'Update', not expected, 'No record to update; expected update=False')

    # ----- DELETE -----
    if target_id:
        try:
            call(model, 'unlink', [target_id])
            deleted = True
        except Exception:
            deleted = False
        expected = 'D' in crud
        record(human_mod, 'Delete', (deleted == expected), f'Deleted={deleted}, Expected={expected}')
    else:
        expected = 'D' in crud
        record(human_mod, 'Delete', not expected, 'No record to delete; expected delete=False')

# ------------------------------------------------------------------
# Summary & verdict
# ------------------------------------------------------------------
total = passed = failed = 0
for _, tests in report['module_results'].items():
    for t in tests:
        total += 1
        if t['passed']:
            passed += 1
        else:
            failed += 1
report['executive_summary'] = {'total_tests': total, 'passed': passed, 'failed': failed}

if failed == 0:
    report['final_verdict'] = '✅ SECURE'
elif failed < total * 0.2:
    report['final_verdict'] = '⚠️ PARTIALLY SECURE (minor issues)'
else:
    report['final_verdict'] = '❌ VULNERABLE (critical breaches)'

print(json.dumps(report, indent=2))
