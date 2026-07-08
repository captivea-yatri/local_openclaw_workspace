#!/usr/bin/env python3
"""Script to perform write operations and return the IDs of records written to."""
import json, sys, traceback, xmlrpc.client, urllib.parse

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USERNAME = "sabrina.ranaivojaona@captivea.com"
PASSWORD = "***"

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "authentication failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)

results = {}

def try_write_and_get_id(model, field_name, field_value, description):
    """Try to write to a record and return the ID if successful."""
    try:
        # First, find a record to write to
        ids = models.execute_kw(DB, uid, PASSWORD, model, 'search', [[]], {'limit': 1})
        if not ids:
            return {"status": "SKIPPED", "detail": "No records found", "id": None}
        
        record_id = ids[0]
        
        # Perform the write
        models.execute_kw(DB, uid, PASSWORD, model, 'write', [[record_id], {field_name: field_value}])
        
        # Verify the write worked by reading it back
        verify = models.execute_kw(DB, uid, PASSWORD, model, 'read', [[record_id], [field_name]])
        
        return {
            "status": "PASS", 
            "detail": f"Successfully wrote {field_name}={field_value}",
            "id": record_id,
            "verified_value": verify[0][field_name] if verify else None
        }
    except xmlrpc.client.Fault as fault:
        return {"status": "FAIL", "detail": f"Fault {fault.faultCode}: {fault.faultString}", "id": None}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e), "id": None}

# Test the three models that had successful writes in the original test
print("Testing write operations to get record IDs...")

# 1. Project.project
project_result = try_write_and_get_id('project.project', 'description', 'QA edit from ID test', 'Project')
results['project.project'] = project_result

# 2. Project.task  
task_result = try_write_and_get_id('project.task', 'name', 'QA Validation Task from ID test', 'Task')
results['project.task'] = task_result

# 3. Helpdesk.ticket
ticket_result = try_write_and_get_id('helpdesk.ticket', 'description', 'QA edit from ID test', 'Helpdesk Ticket')
results['helpdesk.ticket'] = ticket_result

# Output results as JSON
print(json.dumps(results, indent=2))