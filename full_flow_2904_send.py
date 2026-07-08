#!/usr/bin/env python3
"""Full flow for project 2904:
1. Ensure a task exists.
2. Create two timesheet entries (2h, 3h) on the task.
3. Call custom project methods in order:
   - refresh_project_domain_calculation
   - calculate_the_progress_remaining_hours (ignore None)
   - action_get_project_progress_report (log returned action)
4. Ensure a project.progress record exists and set its phase_id.
5. Call action_project_progress_send on the progress record to send the report.
All steps are logged to stdout.
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

def ensure_task(uid, models, project_id):
    # Try to find an existing task for the project
    tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id", "name"], "limit": 1})
    if tasks:
        task = tasks[0]
        log(f"Found existing task ID={task['id']} name={task['name']}")
        return task['id']
    # No task – ensure a phase exists first
    phases = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "limit": 1})
    if not phases:
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
    line_ids = []
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
        line_ids.append(line_id)
    return line_ids

def call_project_methods(uid, models, project_id):
    # refresh_project_domain_calculation (required before progress creation)
    try:
        res = models.execute_kw(DB, uid, PASS, "project.project", "refresh_project_domain_calculation", [project_id])
        log(f"refresh_project_domain_calculation result: {res}")
    except Exception as e:
        log(f"refresh_project_domain_calculation failed: {e}")
    # action_get_project_progress_report (just retrieve the action, no calculation yet)
    try:
        report_action = models.execute_kw(DB, uid, PASS, "project.project", "action_get_project_progress_report", [project_id])
        log(f"action_get_project_progress_report returned: {report_action}")
    except Exception as e:
        log(f"action_get_project_progress_report failed: {e}")
        report_action = None
    return report_action

def ensure_progress_record(uid, models, project_id):
    # Look for an existing project.progress
    existing = models.execute_kw(DB, uid, PASS, "project.progress", "search", [[("project_id", "=", project_id)]])
    if existing:
        prog_id = existing[0]
        log(f"Found existing project.progress ID={prog_id}")
    else:
        prog_id = models.execute_kw(DB, uid, PASS, "project.progress", "create", [{"project_id": project_id}])
        log(f"Created new project.progress ID={prog_id}")
    # Ensure phase_id is set (use first phase of project)
    phases = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id"], "limit": 1})
    if phases:
        phase_id = phases[0]["id"]
        try:
            models.execute_kw(DB, uid, PASS, "project.progress", "write", [[prog_id], {"phase_id": phase_id}])
            log(f"Set phase_id={phase_id} on project.progress ID={prog_id}")
        except Exception as e:
            log(f"Failed to set phase_id on progress record: {e}")
    return prog_id

def send_progress_report(uid, models, progress_id):
    # Call the method that sends the report (if it exists)
    try:
        res = models.execute_kw(DB, uid, PASS, "project.progress", "action_project_progress_send", [progress_id])
        log(f"action_project_progress_send result: {res}")
    except Exception as e:
        log(f"action_project_progress_send failed (method may be missing): {e}")

def main():
    uid, models = connect_admin()
    log(f"Connected as uid={uid}")
    task_id = ensure_task(uid, models, PROJECT_ID)
    create_timesheets(uid, models, task_id, PROJECT_ID)
    report_action = call_project_methods(uid, models, PROJECT_ID)
    progress_id = ensure_progress_record(uid, models, PROJECT_ID)
    # After creating the progress record, calculate remaining hours on it
    try:
        prog_res = models.execute_kw(DB, uid, PASS, "project.progress", "calculate_the_progress_remaining_hours", [progress_id])
        log(f"calculate_the_progress_remaining_hours on progress record result: {prog_res}")
    except Exception as e:
        log(f"calculate_the_progress_remaining_hours on progress record failed: {e}")
    send_progress_report(uid, models, progress_id)
    log("Full flow completed.")

if __name__ == "__main__":
    main()