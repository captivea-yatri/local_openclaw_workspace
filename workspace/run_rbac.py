#!/usr/bin/env python3
import sys, os
# Add the directory containing odoo_rbac_tool.py to path
script_dir = os.path.abspath(os.path.dirname(__file__))
tool_path = os.path.join(script_dir, 'workspace')
if tool_path not in sys.path:
    sys.path.insert(0, tool_path)

try:
    from odoo_rbac_tool import FullDiscovery
except Exception as e:
    print('Failed to import odoo_rbac_tool:', e)
    sys.exit(1)

# Credentials as provided by the user
creds = {
    "TestUser": {
        "url": "https://uriah-apolitical-masako.ngrok-free.dev",
        "db": "odoo19_captivea2",
        "login": "francois.coudreau@captivea.com",
        "password": "a"
    }
}

fd = FullDiscovery()
fd.discover(creds)

for role, tests in fd.all_results.items():
    print(f"\n=== Role: {role} ===")
    for t in tests:
        print(f"{t['category']} | {t['test']} -> {t['result']}")
