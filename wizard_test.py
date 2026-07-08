#!/usr/bin/env python3
import json, sys, time, datetime, ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def log(msg):
    print(msg)

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

def main():
    uid, models = connect_admin()
    ts = int(time.time())
    
    # First, let's get a project to test with - use the most recent one
    projects = models.execute_kw(DB, uid, PASS, "project.project", "search_read", 
                                [], {"fields": ["id", "name"], "limit": 1, "order": "id desc"})
    if not projects:
        log("No projects found!")
        return
        
    project_id = projects[0]["id"]
    project_name = projects[0]["name"]
    log(f"Using project: {project_name} (ID={project_id})")
    
    # Get a phase for this project
    phases = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", 
                              [("project_id", "=", project_id)], 
                              {"fields": ["id", "name"], "limit": 1})
    if not phases:
        log(f"No phases found for project {project_id}!")
        return
        
    phase_id = phases[0]["id"]
    phase_name = phases[0]["name"]
    log(f"Using phase: {phase_name} (ID={phase_id})")
    
    # Count tasks before
    tasks_before = models.execute_kw(DB, uid, PASS, "project.task", "search_count", 
                                    [("project_id", "=", project_id)])
    log(f"Tasks before wizard: {tasks_before}")
    
    # Create wizard with project_id and phase_id
    ctx = {"active_model": "project.project", "active_id": project_id}
    wizard_vals = {
        "project_id": project_id,
        "phase_id": phase_id,
    }
    try:
        wizard_id = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "create", [wizard_vals], {"context": ctx})
        log(f"Wizard created: ID={wizard_id}")
    except Exception as e:
        log(f"Failed to create wizard: {e}")
        return
        
    # Execute the action
    try:
        result = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "action_create_task_from_project", [wizard_id], {"context": ctx})
        log(f"Wizard action executed. Result: {result}")
    except Exception as e:
        log(f"Wizard action failed: {e}")
        # Check if it's the expected "None" fault
        if "cannot marshal None" in str(e):
            log("Got expected 'cannot marshal None' fault - treating as success")
        else:
            return
    
    # Count tasks after
    time.sleep(2)  # Wait a bit
    tasks_after = models.execute_kw(DB, uid, PASS, "project.task", "search_count", 
                                   [("project_id", "=", project_id)])
    log(f"Tasks after wizard: {tasks_after}")
    
    if tasks_after > tasks_before:
        log(f"SUCCESS: Wizard created {tasks_after - tasks_before} new task(s)!")
        # Get the new task(s)
        new_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", 
                                     [("project_id", "=", project_id)], 
                                     {"fields": ["id", "name"], "order": "id desc", "limit": tasks_after - tasks_before})
        for task in new_tasks:
            log(f"  New task: {task['name']} (ID={task['id']})")
    else:
        log("FAILURE: No new tasks created by wizard")
        # Let's see what tasks DO exist
        all_tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", 
                                     [("project_id", "=", project_id)], 
                                     {"fields": ["id", "name", "active"], "limit": 5})
        log(f"Existing tasks in project:")
        for task in all_tasks:
            log(f"  {task['name']} (ID={task['id']}) active={task.get('active', 'N/A')}")

if __name__ == "__main__":
    main()