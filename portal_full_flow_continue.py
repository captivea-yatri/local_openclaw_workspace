#!/usr/bin/env python3
"""Continuation of the portal‑access flow.
   • Reads the partial JSON report created by ``portal_full_flow_test.py``.
   • Completes the missing steps: create a task (using the correct assignee field) and post a feedback message.
   • Writes an updated report with the new IDs.
"""
import json, sys, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB       = "odoo19_captivea2"
ADMIN    = "admin1"
PASS     = "a"

def log(msg):
    print(msg)

def main():
    # --------------------------------------------------
    # Load the partial report from the first script
    # --------------------------------------------------
    report_path = "/home/captivea/.openclaw/workspace/portal_full_flow_test_report.json"
    try:
        with open(report_path) as f:
            data = json.load(f)
        report = data.get("report", {})
        errors = data.get("errors", [])
    except Exception as e:
        log(f"[!] Could not read partial report: {e}")
        return 1

    # --------------------------------------------------
    # Connect as admin
    # --------------------------------------------------
    common = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"))
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        log("[!] Admin authentication failed")
        return 1
    models = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"))
    log(f"[+] Admin UID = {uid}")

    # --------------------------------------------------
    # Extract needed IDs from the partial report
    # --------------------------------------------------
    partner_id = report.get("partner_id")
    project_id = report.get("project_id")
    portal_user_id = report.get("portal_user_id")
    if not all([partner_id, project_id, portal_user_id]):
        log("[!] Missing IDs in the partial report – cannot continue")
        return 1

    # --------------------------------------------------
    # 1️⃣  Determine the correct assignee field for project.task
    # --------------------------------------------------
    fields = models.execute_kw(DB, uid, PASS, "project.task", "fields_get", [], {"attributes": ["type", "string"]})
    # Choose a field that can store a single user ID.
    # Prefer the custom x_default_user_id (used elsewhere), fall back to user_ids (many2many).
    assignee_field = None
    if "x_default_user_id" in fields:
        assignee_field = "x_default_user_id"
    elif "user_ids" in fields:
        assignee_field = "user_ids"
    else:
        log("[!] No suitable assignee field found on project.task")
        return 1
    log(f"[+] Using assignee field '{assignee_field}' for task creation")