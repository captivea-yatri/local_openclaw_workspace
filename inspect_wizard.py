#!/usr/bin/env python3
import ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def connect_admin():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin authentication failed")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

uid, models = connect_admin()
print(f"Connected as uid: {uid}")

# Get fields of project.requirement.wizard
wizard_fields = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "fields_get", [], {})
print("\nWizard fields:")
for field_name, field_info in wizard_fields.items():
    if field_name in ['project_id', 'phase_id']:  # Only show relevant fields
        print(f"  {field_name}: {field_info}")

# Also check project.task fields for reference
task_fields = models.execute_kw(DB, uid, PASS, "project.task", "fields_get", [], {})
print("\nTask assignee-related fields:")
for field_name in ['user_id', 'x_default_user_id']:
    if field_name in task_fields:
        print(f"  {field_name}: {task_fields[field_name]}")