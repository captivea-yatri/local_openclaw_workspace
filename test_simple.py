#!/usr/bin/env python3
import json, sys, traceback, xmlrpc.client, urllib.parse, time

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USERNAME = "admin1"
PASSWORD = "a"

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})

time.sleep(0.2)
if not uid:
    print(json.dumps({"error": "authentication failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)

results = []

def add(tc, module, action, status, detail=""):
    results.append({"tc": tc, "module": module, "action": action, "status": status, "detail": detail})

# Simple test - just read res.partner with specific fields to avoid computed field issues
try:
    # Try reading with just a few basic fields to avoid the computed field issue
    ids = models.execute_kw(
        DB, uid, PASSWORD,
        'res.partner', 'search_read',
        [[]],
        {'fields': ['id', 'name', 'email'], 'limit': 5}
    )
    add(10, 'res.partner', 'Read', 'PASS', f'Found {len(ids)} records')
except Exception as e:
    add(10, 'res.partner', 'Read', 'FAIL', str(e))

print(json.dumps(results, indent=2))