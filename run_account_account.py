#!/usr/bin/env python3
import json, sys, xmlrpc.client, urllib.parse

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USERNAME = "princy.randimbimanana@captivea.com"
PASSWORD = "a"

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print('Authentication failed')
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)

# Search for some account.account records
ids = models.execute_kw(DB, uid, PASSWORD, 'account.account', 'search', [[]], {'limit': 10})
if not ids:
    print('No account.account records found')
    sys.exit(0)
# Read basic fields that are always present: id, code, name
records = models.execute_kw(DB, uid, PASSWORD, 'account.account', 'read', [ids], {'fields': ['id', 'code', 'name']})
# Add a UI link for each record (Odoo web view)
for rec in records:
    rec_id = rec.get('id')
    rec['url'] = f"{ODOO_URL}/web#id={rec_id}&model=account.account&view_type=form"
print(json.dumps(records, indent=2))
