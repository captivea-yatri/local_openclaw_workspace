#!/usr/bin/env python3
"""Test the full progress‑report flow for an existing project (ID = 2904).
Steps:
1️⃣ Find (or create) a task for the project.
2️⃣ Create a couple of timesheet entries on that task (with timesheet_validation context).
3️⃣ Call custom project methods in the required order:
   • refresh_project_domain_calculation
   • calculate_the_progress_remaining_hours
   • action_get_project_progress_report
4️⃣ Create a project.progress record (if not existing) and set its phase_id.
All actions are logged to stdout.
"""
import time, ssl, json
import xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"
PROJECT_ID = 2904

def log(msg):
    print(f"[LOG] {msg}")

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

def find_or_create_task(uid, models, project_id):
    # Look for an existing task in this project
    tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id", "name"], "limit": 1})
    if tasks:
        task = tasks[0]
        log(f"Found existing task ID={task['id']} name={task['name']}")
        return task['id']
    # No task – create one with a default phase
    # Ensure there is at least one phase
    phases = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "limit": 1})
    if not phases:
        # create a simple phase
        phase_id = models.execute_kw(DB, uid, PASS, "project.phase", "create", [{"name": "Default Phase", "project_id": project_id, "active": True, "sequence": 1}])
        log(f"Created default phase ID={phase_id}")
    else:
        phase_id = phases[0]["id"]
    task_vals = {
        "name": f"Test Task for project {project_id}",
        "project_id": project_id,
        "default_phase_id": phase_id,
    }
    task_id = models.execute_kw(DB, uid, PASS, "project.task", "create", [task_vals])
    log(f"Created new task ID={task_id}")
    return task_id

def create_timesheets(uid, models, task_id, project_id):
    now = time.strftime("%Y-%m-%d")
    lines = []
    for hrs in (2.0, 3.0):
        vals = {
            "task_id": task_id,
            "project_id": project_id,
            "date": now,
            "unit_amount": hrs,
            "name": f"Automated TS {hrs}h",
            "user_id": uid,
        }
        line_id = models.execute_kw(DB, uid, PASS, "account.analytic.line", "create", [vals], {"context": {"timesheet_validation": True}})
        log(f"Created timesheet line ID={line_id} for {hrs}h")
        lines.append(line_id)
    return lines

def call_project_methods(uid, models, project_id):
    # refresh_project_domain_calculation
    try:
        res = models.execute_kw(DB, uid, PASS, "project.project", "refresh_project_domain_calculation", [project_id])
        log(f"refresh_project_domain_calculation result: {res}")
    except Exception as e:
        log(f"refresh_project_domain_calculation failed: {e}")
    # calculate_the_progress_remaining_hours
    try:
        res = models.execute_kw(DB, uid, PASS, "project.project", "calculate_the_progress_remaining_hours", [project_id])
        log(f"calculate_the_progress_remaining_hours result: {res}")
    except Exception as e:
        log(f"calculate_the_progress_remaining_hours failed: {e}")
    # action_get_project_progress_report
    try:
        report_action = models.execute_kw(DB, uid, PASS, "project.project", "action_get_project_progress_report", [project_id])
        log(f"action_get_project_progress_report returned: {report_action}")
    except Exception as e:
        log(f"action_get_project_progress_report failed: {e}")

def ensure_progress_record(uid, models, project_id, report_action):
    # Try to find an existing project.progress for this project
    existing = models.execute_kw(DB, uid, PASS, "project.progress", "search", [[("project_id", "=", project_id)]])
    if existing:
        prog_id = existing[0]
        log(f"Found existing project.progress ID={prog_id}")
    else:
        # Create a new progress record – minimal required fields
        vals = {
            "project_id": project_id,
        }
        prog_id = models.execute_kw(DB, uid, PASS, "project.progress", "create", [vals])
        log(f"Created new project.progress ID={prog_id}")
    # Set phase_id if the report action provides a default
    # Fetch a phase for the project (use first)
    phase = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "limit": 1})
    if phase:
        phase_id = phase[0]["id"]
        try:
            models.execute_kw(DB, uid, PASS, "project.progress", "write", [[prog_id], {"phase_id": phase_id}])
            log(f"Set phase_id={phase_id} on project.progress ID={prog_id}")
        except Exception as fe:
            log(f"Failed to set phase_id on progress record: {fe}")
    return prog_id

def main():
    uid, models = connect_admin()
    log(f"Connected as uid={uid}")
    # 1️⃣ Find or create a task
    task_id = find_or_create_task(uid, models, PROJECT_ID)
    # 2️⃣ Create timesheet entries
    create_timesheets(uid, models, task_id, PROJECT_ID)
    # 3️⃣ Call custom project methods + get report action
    call_project_methods(uid, models, PROJECT_ID)
    # 4️⃣ Ensure a project.progress record exists and set its phase_id
    # (We just call action_get_project_progress_report again to get the action dict)
    try:
        report_action = models.execute_kw(DB, uid, PASS, "project.project", "action_get_project_progress_report", [PROJECT_ID])
    except Exception:
        report_action = None
    ensure_progress_record(uid, models, PROJECT_ID, report_action)
    log("Test flow completed.")

if __name__ == "__main__":
    main()
