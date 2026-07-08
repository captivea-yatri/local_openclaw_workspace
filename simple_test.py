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

# Create a project
project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [{
    "name": "Test Project",
}])
print(f"Created project ID: {project_id} (type: {type(project_id)})")

# Try to read it back
try:
    project = models.execute_kw(DB, uid, PASS, "project.project", "read", [[project_id]], {"fields": ["name"]})
    print(f"Project read: {project}")
except Exception as e:
    print(f"Failed to read project: {e}")

# Try to search for it with domain
try:
    ids = models.execute_kw(DB, uid, PASS, "project.project", "search", [[("id", "=", project_id)]], {})
    print(f"Search results: {ids}")
except Exception as e:
    print(f"Search failed: {e}")
    print(f"Error type: {type(e)}")

# Try to count tasks on this project (should be 0)
try:
    count = models.execute_kw(DB, uid, PASS, "project.task", "search_count", [[("project_id", "=", project_id)]], {})
    print(f"Task count: {count}")
except Exception as e:
    print(f"Task count failed: {e}")
    # Let's try a different approach - get all tasks and filter manually
    try:
        all_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [], {"fields": ["id", "project_id"], "limit": 5})
        print(f"First 5 tasks: {all_tasks}")
        for task in all_tasks:
            proj_id = task.get('project_id')
            if proj_id:
                print(f"  Task {task['id']} is in project {proj_id[0] if isinstance(proj_id, (list, tuple)) else proj_id}")
    except Exception as e2:
        print(f"Also failed to get tasks: {e2}")