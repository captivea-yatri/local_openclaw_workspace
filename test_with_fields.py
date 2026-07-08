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

# Create a partner first (needed for the fields)
partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [{
    "name": "Test Partner",
    "email": "test@example.com",
}])
print(f"Created partner ID: {partner_id}")

# Get admin company
admin_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[uid]], {"fields": ["company_id"]})[0]
admin_company_id = admin_user.get("company_id")[0]
print(f"Admin company ID: {admin_company_id}")

# Create a project with the same fields as in debug script
project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [{
    "name": f"Test Project {int(__import__('time').time())}",
    "partner_id": partner_id,
    "company_id": admin_company_id,
    "signatory_progress_report_partner_id": partner_id,
}])
print(f"Created project ID: {project_id} (type: {type(project_id)})")

# Try to read it back
try:
    project = models.execute_kw(DB, uid, PASS, "project.project", "read", [[project_id]], {"fields": ["id", "name", "partner_id", "company_id", "signatory_progress_report_partner_id"]})
    print(f"Project read: {project}")
except Exception as e:
    print(f"Failed to read project: {e}")

# Try to search for it with domain
try:
    ids = models.execute_kw(DB, uid, PASS, "project.project", "search", [[("id", "=", project_id)]], {})
    print(f"Search results: {ids}")
except Exception as e:
    print(f"Search failed: {e}")

# Try to count tasks on this project (should be 0)
try:
    count = models.execute_kw(DB, uid, PASS, "project.task", "search_count", [[("project_id", "=", project_id)]], {})
    print(f"Task count: {count}")
except Exception as e:
    print(f"Task count failed: {e}")
    print(f"Error type: {type(e)}")
    # Let's try to get the error details
    import traceback
    traceback.print_exc()