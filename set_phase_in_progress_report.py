#!/usr/bin/env python3
"""Set the phase_id on the project.progress report for project 2914.
   Assumes the report record ID is known (7948) from the previous step.
"""
import ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

def log(msg):
    print(f"[LOG] {msg}")

def connect_admin():
    common = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/common"),
        context=ssl._create_unverified_context()
    )
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Admin auth failed")
    models = xmlrpc.client.ServerProxy(
        urljoin(ODOO_URL, "/xmlrpc/2/object"),
        context=ssl._create_unverified_context()
    )
    return uid, models

def main():
    uid, models = connect_admin()
    project_id = 2914
    report_id = 7948  # ID of the project.progress record we just created
    # Find a phase for the project (any)
    phases = models.execute_kw(DB, uid, PASS, "project.phase", "search_read", [[("project_id", "=", project_id)]], {"fields": ["id", "name"], "limit": 1})
    if not phases:
        log("No phase found for project – cannot set phase_id.")
        return
    phase_id = phases[0]["id"]
    log(f"Using phase ID={phase_id} for project {project_id}")
    # Update the project.progress record
    try:
        res = models.execute_kw(DB, uid, PASS, "project.progress", "write", [[report_id], {"phase_id": phase_id}])
        log(f"Successfully set phase_id={phase_id} on project.progress ID={report_id}: {res}")
    except Exception as e:
        log(f"Failed to set phase_id: {e}")

if __name__ == "__main__":
    main()
