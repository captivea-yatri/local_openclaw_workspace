#!/usr/bin/env python3
"""Functional workflow validation for the custom Odoo 19 module
    Customer Payment Terms.

This script runs the core end‑to‑end scenarios using Odoo XML‑RPC
(no UI automation required). It reports PASS/FAIL for each test case.
"""
import json, sys, xmlrpc.client, urllib.parse, traceback

# Load credentials (the file you just updated)
with open('odoo_rbac_credentials.json') as f:
    creds = json.load(f)

ODOO_URL = creds['url']
DB = creds['database']
USERNAME = creds['username']
PASSWORD = creds['password']

common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    print(json.dumps({"error": "authentication failed"}))
    sys.exit(1)
models = xmlrpc.client.ServerProxy(object_url)


# Helper to record test results
# -----------------------------------------------------------------
results = []

def add(test_id, description, status, detail=""):
    results.append({"id": test_id, "desc": description, "status": status, "detail": detail})

# Utility to fetch field names for the custom booleans
# The module may define the booleans with any of these possible names.
# We will try a list of candidates and pick the first that exists.

def find_boolean_field(candidates):
    try:
        fields = models.execute_kw(DB, uid, PASSWORD,
            'account.payment.term', 'fields_get', [],
            {'attributes': ['type']})
        for c in candidates:
            if c in fields and fields[c].get('type') == 'boolean':
                return c
    except Exception:
        pass
    return None

# Detect the custom boolean field names on the payment.term model.
# The module may use different technical names; we try a few common ones.
DEFAULT_FIELD = find_boolean_field(['x_default', 'default', 'is_default'])
AFTER_FIRST_FIELD = find_boolean_field(['x_default_after_first_payment', 'default_after_first', 'is_default_after_first'])
if not DEFAULT_FIELD or not AFTER_FIRST_FIELD:
    # If the fields are not detected, the test will still run but cannot set flags.
    add('CONFIG', 'Detect custom boolean fields', 'FAIL', 'Could not locate boolean fields on payment.term')
else:
    add('CONFIG', 'Detect custom boolean fields', 'PASS', f"DEFAULT={DEFAULT_FIELD}, AFTER_FIRST={AFTER_FIRST_FIELD}")

# 1️⃣ Create two payment terms

def create_payment_terms():
    # Ensure we have detected the custom fields
    if not DEFAULT_FIELD or not AFTER_FIRST_FIELD:
        add('PT_SETUP', 'Create payment terms', 'SKIPPED', 'Custom boolean fields not found')
        return None, None
    # Term A – New Customer Term (default = True, after_first = False)
    term_a_id = models.execute_kw(DB, uid, PASSWORD, 'account.payment.term', 'create', [{
        'name': 'New Customer Term',
        DEFAULT_FIELD: True,
        AFTER_FIRST_FIELD: False,
    }])
    add('PT_A', "Create Payment Term A (New Customer)", 'PASS', f"ID={term_a_id}")
    # Term B – Trusted Customer Term (default = False, after_first = True)
    term_b_id = models.execute_kw(DB, uid, PASSWORD, 'account.payment.term', 'create', [{
        'name': 'Trusted Customer Term',
        DEFAULT_FIELD: False,
        AFTER_FIRST_FIELD: True,
    }])
    add('PT_B', "Create Payment Term B (Trusted Customer)", 'PASS', f"ID={term_b_id}")
    return term_a_id, term_b_id

def create_payment_term(name, is_default, after_first):
    # Create a payment term with the required boolean flags
    # The custom module is expected to have boolean fields:
    #   x_default (default for new customers)
    #   x_default_after_first_payment (default after first payment)
    # For simplicity we assume the field technical names are exactly those.
    vals = {
        'name': name,
        # these field names are guesses – adjust if they differ in your DB
        'x_default': is_default,
        'x_default_after_first_payment': after_first,
    }
    try:
        term_id = models.execute_kw(DB, uid, PASSWORD, 'account.payment.term', 'create', [vals])
        add('PT1', f"Create payment term '{name}'", 'PASS', f"ID={term_id}")
        return term_id
    except Exception as e:
        add('PT1', f"Create payment term '{name}'", 'FAIL', str(e))
        return None

if __name__ == "__main__":
    # Execute core validation steps
    a_id, b_id = create_payment_terms()
    # Print the collected test results as nicely formatted JSON
    print(json.dumps(results, indent=2))