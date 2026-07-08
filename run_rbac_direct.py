#!/usr/bin/env python3
import sys, os
# Ensure the inner workspace subdirectory is in sys.path so we load the full implementation
script_dir = os.path.abspath(os.path.dirname(__file__))
inner_path = os.path.join(script_dir, 'workspace')
if inner_path not in sys.path:
    sys.path.insert(0, inner_path)
# Also add script_dir as fallback (contains a stub version we want to override)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from odoo_rbac_tool import FullDiscovery

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
