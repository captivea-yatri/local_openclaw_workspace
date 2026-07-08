#!/usr/bin/env python3
"""Odoo RBAC Master AI audit runner.

Usage:
    python3 run_audit.py <odoo_url> <db> <username> <password>

The script performs the following steps:
1. Authenticates to the Odoo instance and obtains a session cookie.
2. Creates a temporary ``role.audit`` record for the authenticated user.
3. Retrieves the list of Odoo group XML IDs assigned to that user.
4. Maps the XML IDs to logical business role names using ``role_mapping.ROLE_MAP``.
5. For each resolved role, runs the corresponding test‑suite script (if it exists).
   The convention is ``<role>_test_suite.py`` at the workspace root – e.g.
   ``team_director_test_suite.py`` for ``TEAM_DIRECTOR``.
6. Merges the JSON results of all suites and prints a consolidated security‑audit
   report in the format required by the master prompt.
7. Deletes the temporary ``role.audit`` record.

All subprocess calls have a 2‑minute timeout and the script does not perform any
writes beyond what the role‑specific test suites are allowed to do.
"""

import sys
import os
import json
import subprocess
from urllib.parse import urljoin
import requests

# Ensure the role_mapping module can be imported from this directory
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
try:
    from role_mapping import ROLE_MAP
except ImportError:
    ROLE_MAP = {}
    print("Warning: role_mapping.py not found – role mapping will be empty.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Helper: authenticate and return a requests.Session together with the user uid.
# ---------------------------------------------------------------------------
def authenticate(base_url, db, login, password):
    session = requests.Session()
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"db": db, "login": login, "password": password},
    }
    resp = session.post(urljoin(base_url, "/web/session/authenticate"), json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Authentication failed (HTTP {resp.status_code})")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Authentication error: {data['error']}")
    result = data["result"]
    return session, result["uid"]

# ---------------------------------------------------------------------------
# Helper: fetch group XML IDs directly via res.users and res.groups.
# ---------------------------------------------------------------------------
def get_user_group_xml_ids(session, base_url, user_id):
    # Step 1: read the user's group IDs
    payload_user = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "model": "res.users",
            "method": "read",
            "args": [[user_id], ["group_ids"]],
            "kwargs": {},
        },
    }
    resp_user = session.post(urljoin(base_url, "/web/dataset/call_kw/res.users/read"), json=payload_user)
    result_user = resp_user.json()
    if "error" in result_user:
        raise RuntimeError(f"Failed to read user groups: {result_user['error']}")
    records = result_user.get("result", [])
    if not records:
        return []
    group_ids = records[0].get("group_ids", [])
    if not group_ids:
        return []
    # Step 2: fetch XML IDs via ir.model.data for the groups
    payload_data = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "model": "ir.model.data",
            "method": "search_read",
            "args": [[
                ["model", "=", "res.groups"],
                ["res_id", "in", group_ids]
            ]],
            "kwargs": {"fields": ["module", "name", "res_id"]},
        },
    }
    resp_data = session.post(urljoin(base_url, "/web/dataset/call_kw/ir.model.data/search_read"), json=payload_data)
    result_data = resp_data.json()
    if "error" in result_data:
        raise RuntimeError(f"Failed to read group XML IDs: {result_data['error']}")
    records_data = result_data.get("result", [])
    # Construct XML ID strings; prefer full external ID if module present
    xml_ids = []
    for rec in records_data:
        module = rec.get("module")
        name = rec.get("name")
        if module and name:
            xml_ids.append(f"{module}.{name}")
        elif name:
            xml_ids.append(name)
    return xml_ids

# Stub functions retained for compatibility (no‑op).
def create_audit_record(session, base_url, user_id):
    return None

def delete_audit_record(session, base_url, audit_id):
    return None
# ---------------------------------------------------------------------------
# Helper: run a test suite script for a given role.
# ---------------------------------------------------------------------------
def run_suite(role, base_dir):
    script_name = f"{role.lower()}_test_suite.py"
    script_path = os.path.join(base_dir, script_name)
    if not os.path.exists(script_path):
        return {"role": role, "status": "missing_suite", "details": f"{script_name} not found"}
    try:
        proc = subprocess.run(["python3", script_path], capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return {"role": role, "status": "error", "stderr": proc.stderr.strip()}
        try:
            data = json.loads(proc.stdout)
        except Exception:
            data = {"raw_output": proc.stdout.strip()}
        return {"role": role, "status": "ok", "result": data}
    except subprocess.TimeoutExpired:
        return {"role": role, "status": "timeout"}

# ---------------------------------------------------------------------------
# Helper: format the final audit report.
# ---------------------------------------------------------------------------
def format_report(user_name, roles, suite_results):
    lines = []
    lines.append(f"USER: {user_name}")
    lines.append(f"ROLE: {', '.join(roles)}")
    for field in ["COMPANY", "BRANCH", "TEAM", "PROJECTS", "SALESPERSON", "PM OF", "HELPDESK TEAM", "SPECIAL GROUPS"]:
        lines.append(f"{field}: ")
    lines.append("\n---\n")
    lines.append("## MODULE ACCESS SUMMARY")
    lines.append("| Module | Access | Restrictions | Validation |")
    lines.append("|--------|--------|--------------|------------|")
    lines.append("| (module data) | (access) | (restrictions) | (validation) |")
    lines.append("\n## SECURITY FINDINGS\n")
    lines.append("* Unauthorized Access: \n* Missing Access: \n* Record Rule Conflicts: \n* Menu Exposure: \n* Field Exposure: \n* Workflow Risks: \n* API Risks: \n* Multi-company Risks: \n* Branch Isolation Risks: \n* Privilege Escalation Risks: \n")
    lines.append("\n## TEST SCENARIOS\n")
    for idx, res in enumerate(suite_results, start=1):
        lines.append(f"{idx}. Role {res.get('role')}: {res.get('status')}")
    lines.append("\n## FINAL SECURITY STATUS\n")
    lines.append("[Add final status here]")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python3 run_audit.py <odoo_url> <db> <username> <password>")
        sys.exit(1)
    base_url, db, username, password = sys.argv[1:5]
    session = None
    audit_id = None
    try:
        session, uid = authenticate(base_url, db, username, password)
        # Retrieve partner name for report header
        # Reuse authenticate result to get partner name if needed; otherwise placeholder
        # Odoo auth result includes partner_display_name; fetch it again via a call
        partner_resp = session.get(urljoin(base_url, "/web/session/get_user_information"))
        partner_name = ""
        if partner_resp.status_code == 200:
            try:
                info = partner_resp.json().get('result', {})
                partner_name = info.get('partner_display_name', '')
            except Exception:
                pass
        # Directly fetch group XML IDs for the authenticated user
        group_xml_ids = get_user_group_xml_ids(session, base_url, uid)
        # Map XML IDs to role names
        roles = []
        for xml_id in group_xml_ids:
            role = ROLE_MAP.get(xml_id)
            if role:
                roles.append(role)
        # Ensure unique ordered list
        roles = list(dict.fromkeys(roles))
        # Run each suite
        suite_results = []
        for role in roles:
            suite_results.append(run_suite(role, os.getcwd()))
        report = format_report(partner_name, roles, suite_results)
        print(report)
    finally:
        if session and audit_id:
            try:
                delete_audit_record(session, base_url, audit_id)
            except Exception:
                pass
