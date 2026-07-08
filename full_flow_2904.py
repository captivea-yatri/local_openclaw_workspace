#!/usr/bin/env python3
"""Full end‑to‑end progress‑report flow for project 2904.
Steps:
1️⃣ Ensure a task exists for the project.
2️⃣ Create two timesheet entries (2 h & 3 h) on that task (using timesheet_validation context).
3️⃣ Call custom project methods in the exact order required:
   • refresh_project_domain_calculation
   • calculate_the_progress_remaining_hours (ignore None return)
   • action_get_project_progress_report
4️⃣ Ensure a `project.progress` record exists and set its `phase_id`.
5️⃣ Log the final action dict for the report.
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
    # Try to fetch an existing task
    tasks = models.execute_kw(DB, uid, PASS, "project.task", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id", "name"], "limit": 1})
    if tasks:
        task = tasks[0]
        log(f"Found existing task ID={task['id']} name={task['name']}")
        return task['id']
    # No task – need a phase first
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
    log