#!/usr/bin/env python3
"""Parametrised Odoo role‑matrix test.
Usage:
    python3 test_odoo_multi.py \
        --url <ODOO_URL> --db <DB> \
        --user <USERNAME> --pwd <PASSWORD> \
        --role <ROLE_NAME>
The script loads the role matrix, maps human‑module names to Odoo model names,
executes CRUD checks according to the CRUD list defined for the role, and
prints a JSON report to stdout.
"""

import argparse, json, sys, xmlrpc.client, datetime

# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Matrix‑driven Odoo role audit")
parser.add_argument("--url", required=True, help="Odoo base URL")
parser.add_argument("--db", required=True, help="Database name")
parser.add_argument("--user", required=True, help="Username (email)")
parser.add_argument("--pwd", required=True, help="Password")
parser.add_argument("--role", required=True, help="Role name as in role_matrix_by_role.json")
args = parser.parse_args()

ODOO_URL = args.url.rstrip('/')
DB = args.db
USERNAME = args.user
PASSWORD = args.pwd
ROLE_NAME = args.role

# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "Authentication failed"}))
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def call(model, method, *args, **kwargs):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args, kwargs)

# ---------------------------------------------------------------------------
# Load role matrix and pick the role entry
# ---------------------------------------------------------------------------
with open('role_matrix_by_role.json') as f:
    role_matrix = json.load(f)
role_entry = role_matrix.get(ROLE_NAME, {})

# Human‑module → Odoo model mapping (same as in role_based_audit.py)
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

# Helper to find a writable "name"‑like field for create/update operations
def get_name_field(model):
    try:
        fields = call(model, 'fields_get', [], {'attributes': ['type', 'required']})
    except Exception:
        return None
    for fname, finfo in fields.items():
        if finfo.get('required') and finfo.get('type') == 'char':
            return fname
    return 'name' if 'name' in fields else None

# ---------------------------------------------------------------------------
# Reporting container
# ---------------------------------------------------------------------------
report = {
