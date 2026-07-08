#!/usr/bin/env python3
"""Full functional automation for Odoo role‑matrix testing.

This script performs the following steps:
1. Load Odoo connection info and per‑user passwords from `odoo_rbac_credentials.json`.
2. Load the role matrix from `role_matrix_by_role.json`.
3. (Optional) Load a explicit user‑>role map from `user_role_map.json`.  If the map is missing the script will infer the role by querying Odoo groups.
4. For every user in the credentials file it:
   a. Determines the role to test.
   b. Executes the matrix‑driven test script `test_odoo_multi.py` in an isolated subprocess.
   c. Captures the JSON report produced by the test script.
5. Aggregates all per‑user reports into a single HTML dashboard (`all_users_report.html`).
6. (Optional) Writes a simple summary JSON file (`all_users_summary.json`).

The script is deliberately self‑contained – it only requires the standard library
and the `xmlrpc.client` module (already present in the OpenClaw VM).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration – paths relative to the workspace root
# ---------------------------------------------------------------------------
WORKSPACE = Path(__file__).parent
CRED_PATH = WORKSPACE / "odoo_rbac_credentials.json"
MATRIX_PATH = WORKSPACE / "role_matrix_by_role.json"
ROLE_MAP_PATH = WORKSPACE / "user_role_map.json"  # optional
TEST_SCRIPT = WORKSPACE / "test_odoo_multi.py"
HTML_REPORT = WORKSPACE / "all_users_report.html"
JSON_SUMMARY = WORKSPACE / "all_users_summary.json"

# ---------------------------------------------------------------------------
# Helper: read a JSON file (exit with a clear error if missing)
# ---------------------------------------------------------------------------
def load_json(path: Path):
    if not path.is_file():
        print(f"[ERROR] Missing required file: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Load credentials & matrix
# ---------------------------------------------------------------------------
creds = load_json(CRED_PATH)
matrix = load_json(MATRIX_PATH)
role_map = {}
if ROLE_MAP_PATH.is_file():
    role_map = load_json(ROLE_MAP_PATH)
else:
    role_map = {}

# ---------------------------------------------------------------------------
# Helper: infer role from Odoo groups (fallback when not in role_map)
# ---------------------------------------------------------------------------
def infer_role_from_groups(url, db, username, password, matrix_keys):
    import xmlrpc.client
    try:
        common = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return None
        obj = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/object")
        groups = obj.execute_kw(db, uid, password, 'res.users', 'read', [uid], {'fields': ['groups_id']})
        group_ids = groups[0].get('groups_id', [])
        # read group names
        groups_info = obj.execute_kw(db, uid, password, 'res.groups', 'read', [group_ids], {'fields': ['name']})
        for g in groups_info:
            name = g.get('name')
            if name in matrix_keys:
                return name
    except Exception as e:
        print(f"[WARN] Could not infer role for {username}: {e}", file=sys.stderr)
    return None

# ---------------------------------------------------------------------------
# Main loop – run test for each user in credentials
# ---------------------------------------------------------------------------
reports = []
url = creds.get('url') or creds.get('ODOO_URL') or ''
# support both key names: 'database' or 'DB'
db = creds.get('database') or creds.get('DB') or ''
# credentials file may hold a single username/password or a dict of many.
# In the current file we have a single entry, but we also support a dict under 'creds'.
user_pass_dict = {}
if 'username' in creds and 'p***ssword' in creds:
    user_pass_dict[creds['username']] = creds['p***ssword']
if 'creds' in creds:
    # expecting mapping email->password
    user_pass_dict.update(creds['creds'])

matrix_keys = set(matrix.keys())

for email, pwd in user_pass_dict.items():
    role = role_map.get(email)
    if not role:
        role = infer_role_from_groups(url, db, email, pwd, matrix_keys)
        if not role:
            # fallback to a safe default (e.g., 'Administrative')
            role = 'Administrative'
    print(f"[INFO] Running matrix test for {email} (role: {role})")
    # Build command line for test_odoo_multi.py
    cmd = [
        sys.executable, str(TEST_SCRIPT),
        '--url', url,
        '--db', db,
        '--user', email,
        '--pwd', pwd,
        '--role', role
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if completed.returncode != 0:
            print(f"[ERROR] Test script failed for {email}: {completed.stderr}", file=sys.stderr)
            continue
        # The script prints a JSON object on stdout; parse the last line that looks like JSON.
        output = completed.stdout.strip()
        # Some scripts may print extra logs; find the first line that starts with '{'
        json_str = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('{'):
                json_str = line
                break
        if not json_str:
            print(f"[WARN] No JSON output for {email}", file=sys.stderr)
            continue
        report = json.loads(json_str)
        report['user'] = email
        report['role'] = role
        reports.append(report)
    except Exception as e:
        print(f"[WARN] Failed to process output for {email}: {e}", file=sys.stderr)
        continue

# ---------------------------------------------------------------------------
# Helper: generate HTML dashboard from the collected reports
# ---------------------------------------------------------------------------
def build_html(reports):
    html = []
    html.append('<!DOCTYPE html>')
    html.append('<html lang="en"><head><meta charset="UTF-8"><title>All‑Users Odoo RBAC Dashboard</title>')
    html.append('<style>body{font-family:Arial,Helvetica,sans-serif;margin:20px;}')
    html.append('h1{color:#2c3e50;} table{border-collapse:collapse;width:100%;margin-bottom:30px;} th,td{border:1px solid #ddd;padding:8px;text-align:left;} th{background:#f4f4f4;} .pass{color:#27ae60;font-weight:bold;} .fail{color:#c0392b;font-weight:bold;}</style>')
    html.append('</head><body>')
    html.append(f'<h1>All‑Users Odoo RBAC Dashboard</h1>')
    html.append(f'<p>Generated on {datetime.utcnow().isoformat()} UTC</p>')
    # overall summary
    total_tests = sum(r['executive_summary']['total_tests'] for r in reports)
    total_pass = sum(r['executive_summary']['passed'] for r in reports)
    total_fail = sum(r['executive_summary']['failed'] for r in reports)
    html.append(f'<div><strong>Overall:</strong> Users={len(reports)} | Tests={total_tests} | Passed=<span class="pass">{total_pass}</span> | Failed=<span class="fail">{total_fail}</span></div>')
    # per‑user sections
    for rep in reports:
        html.append(f'<h2>User: {rep["user"]} (Role: {rep["role"]})</h2>')
        html.append('<table><thead><tr><th>Module</th><th>Read</th><th>Create</th><th>Update</th><th>Delete</th></tr></thead><tbody>')
        for mod, tests in rep['module_results'].items():
            # each `tests` list contains 4 dicts in order: Read, Create, Update, Delete
            cells = []
            for t in tests:
                cls = 'pass' if t['passed'] else 'fail'
                cells.append(f'<td class="{cls}">{"PASS" if t["passed"] else "FAIL"}<br>{t["details"]}</td>')
            html.append(f'<tr><td>{mod}</td>{"".join(cells)}</tr>')
        html.append('</tbody></table>')
    html.append('</body></html>')
    return '\n'.join(html)

# ---------------------------------------------------------------------------
# Write reports
# ---------------------------------------------------------------------------
if reports:
    html_content = build_html(reports)
    with open(HTML_REPORT, 'w') as f:
        f.write(html_content)
    # also write a simple JSON summary for programmatic consumption
    summary = {
        'generated': datetime.utcnow().isoformat(),
        'total_users': len(reports),
        'total_tests': total_tests,
        'passed': total_pass,
        'failed': total_fail,
        'reports': reports,
    }
    with open(JSON_SUMMARY, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"[INFO] Dashboard written to {HTML_REPORT}")
    print(f"[INFO] Summary JSON written to {JSON_SUMMARY}")
else:
    print('[WARN] No reports were generated.')
