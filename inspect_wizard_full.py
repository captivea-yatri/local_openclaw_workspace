#!/usr/bin/env python3
import ssl, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://aflutter-marxism-creamer.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"

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

uid, models = connect_admin()
print(f"Connected as uid: {uid}")

# Get ALL fields of project.requirement.wizard
wizard_fields = models.execute_kw(DB, uid, PASS, "project.requirement.wizard", "fields_get", [], {})
print(f"\nTotal fields: {len(wizard_fields)}")
print("\nAll wizard fields:")
for field_name, field_info in sorted(wizard_fields.items()):
    req = "REQUIRED" if field_info.get('required') else "optional"
    print(f"  {field_name:20} {req:10} {field_info.get('type', 'unknown'):15} {field_info.get('string', '')}")
    
    # Show relation if it's a relational field
    if field_info.get('type') in ('many2one', 'one2many', 'many2many'):
        relation = field_info.get('relation')
        if relation:
            print(f"                    -> relation: {relation}")