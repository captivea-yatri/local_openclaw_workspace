#!/usr/bin/env python3
import json, sys, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def log(msg):
    print(f"[DEBUG] {msg}")

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

def find_portal_group(models, uid):
    groups = models.execute_kw(
        DB, uid, PASS, "res.groups", "search_read",
        [[("name", "=", "Portal")]],
        {"fields": ["id"], "limit": 1}
    )
    return groups[0]["id"] if groups else None

def detect_assignee_field(models, uid):
    fields = models.execute_kw(
        DB, uid, PASS, "project.task", "fields_get", [], {"attributes": ["type"]}
    )
    return "x_default_user_id" if "x_default_user_id" in fields else "user_id"

def main():
    uid, models = connect_admin()
    ts = int(time.time())
    email = f"debug_user_{ts}@example.com"
    
    log("Starting debug test...")
    
    # Create minimal setup for testing
    # Partner
    partner_id = models.execute_kw(DB, uid, PASS, "res.partner", "create", [{
        "name": f"Debug Partner {ts}",
        "email": email,
        "customer_rank": 1,
    }])
    log(f"Partner created: {partner_id}")
    
    # Portal user
    portal_group_id = find_portal_group(models, uid)
    portal_user_vals = {
        "login": email,
        "partner_id": partner_id,
        "password": "a",
        "share": True,
    }
    if portal_group_id:
        portal_user_vals["group_ids"] = [(6, 0, [portal_group_id])]
    else:
        portal_user_vals["group_ids"] = [(5,)]
    portal_user_id = models.execute_kw(DB, uid, PASS, "res.users", "create", [portal_user_vals])
    log(f"Portal user created: {portal_user_id}")
    
    # Get admin company
    admin_user = models.execute_kw(DB, uid, PASS, "res.users", "read", [[uid]], {"fields": ["company_id"]})[0]
    admin_company_id = admin_user.get("company_id")[0]
    
    # Sales order
    product_id = 2002
    payment_terms = models.execute_kw(DB, uid, PASS, "account.payment.term", "search_read", [[("name", "ilike", "Net"), ("company_id", "=", admin_company_id)]], {"fields": ["id"], "limit": 1})
    payment_term_id = payment_terms[0]["id"] if payment_terms else False
    so_id = models.execute_kw(DB, uid, PASS, "sale.order", "create", [{
        "partner_id": partner_id,
        "company_id": admin_company_id,
        "team_id": False,
        "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1})],
        "payment_term_id": payment_term_id,
    }])
    log(f"Sales order created: {so_id}")
    
    # Get or create project
    so_data = models.execute_kw(DB, uid, PASS, "sale.order", "read", [[so_id]], {"fields": ["project_id"]})[0]
    project_id = so_data.get("project_id")
    if project_id:
        project_id = project_id[0] if isinstance(project_id, (list, tuple)) else project_id
        log(f"Project found via SO: {project_id}")
        # Update required fields
        models.execute_kw(DB, uid, PASS, "project.project", "write", [[project_id], {
            "company_id": admin_company_id,
            "signatory_progress_report_partner_id": partner_id,
        }])
    else:
        project_id = models.execute_kw(DB, uid, PASS, "project.project", "create", [{
            "name": f"Debug Project {ts}",
            "partner_id": partner_id,
            "company_id": admin_company_id,
            "signatory_progress_report_partner_id": partner_id,
        }])
        log(f"Project created: {project_id}")
    
    # Create phase
    phase_id = models.execute_kw(DB, uid, PASS, "project.phase", "create", [{
        "name": "Debug Phase",
        "project_id": project_id,
        "active": True,
        "sequence": 1,
    }])
    log(f"Phase created: {phase_id}")
    
    # Count tasks before wizard
    tasks_before = models.execute_kw(DB, uid, PASS, "project.task", "search_count", [("project_id", "=", project_id)])
    log(f"Tasks before wizard: {tasks_before}")
    
    # Create wizard
    ctx = {"active_model": "project.project", "active_id": project_id}
    wizard_vals = {
        "project_id": project_id,
        "phase_id": phase_id,
    }
    try:
        wizard_id = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "create", [wizard_vals], {"context": ctx})
        log(f"Wizard created: {wizard_id}")
    except Exception as e:
        log(f"Failed to create wizard: {e}")
        return
        
    # Execute wizard action
    try:
        result = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "action_create_task_from_project", [wizard_id], {"context": ctx})
        log(f"Wizard action executed. Result: {result}")
    except xmlrpc.client.Fault as wf:
        if wf.faultCode == 1 and "cannot marshal None" in wf.faultString:
            log("Wizard action returned None (expected)")
        else:
            log(f"Wizard action fault: {wf}")
            return
    except Exception as e:
        log(f"Wizard action failed: {e}")
        return
    
    # Wait and check tasks after
    time.sleep(3)
    tasks_after = models.execute_kw(DB, uid, PASS, "project.task", "search_count", [("project_id", "=", project_id)])
    log(f"Tasks after wizard: {tasks_after}")
    
    if tasks_after > tasks_before:
        log(f"SUCCESS: Created {tasks_after - tasks_before} task(s)!")
        # Get details of new tasks
        new_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", 
                                     [("project_id", "=", project_id)], 
                                     {"fields": ["id", "name", "user_id", "x_default_user_id", "phase_id"], 
                                      "order": "id desc", "limit": tasks_after - tasks_before})
        for task in new_tasks:
            log(f"  Task: {task['name']} (ID={task['id']})")
            log(f"    Assignee (user_id): {task.get('user_id')}")
            log(f"    Assignee (x_default_user_id): {task.get('x_default_user_id')}")
            log(f"    Phase ID: {task.get('phase_id')}")
    else:
        log("FAILURE: No tasks created by wizard")
        # Debug: let's see what tasks exist
        all_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", 
                                     [("project_id", "=", project_id)], 
                                     {"fields": ["id", "name", "active"], "limit": 10})
        log(f"All tasks in project ({len(all_tasks)}):")
        for task in all_tasks:
            log(f"  {task['name']} (ID={task['id']}) active={task.get('active', 'N/A')}")
        
        # Also check if there are any tasks created recently across ALL projects
        recent_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", 
                                        [], 
                                        {"fields": ["id", "name", "project_id", "create_date"], 
                                         "order": "create_date desc", "limit": 5})
        log(f"Recent tasks across all projects:")
        for task in recent_tasks:
            proj_id = task.get('project_id')
            proj_name = proj_id[1] if isinstance(proj_id, (list, tuple)) and len(proj_id) > 1 else str(proj_id) if proj_id else 'None'
            log(f"  {task['name']} (ID={task['id']}) in project {proj_name} created {task.get('create_date')}")

if __name__ == "__main__":
    main()