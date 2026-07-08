#!/usr/bin/env python3
"""Simple Odoo connection test using only the Python standard library.

Replace the placeholder values with your real credentials before running.
"""
import sys
import xmlrpc.client
import urllib.parse

# ==== USER CONFIGURATION ====
ODOO_URL = "https://staging-odoo19-captivea.odoo.com"  # Base URL without trailing /odoo
DB = "captivea-staging-odoo19-31833465"
USERNAME = "lucka.rasoanaivo@captivea.com"
PASSWORD = "a"
# ============================

def main():
    # Odoo XML-RPC endpoints
    common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + "/", "xmlrpc/2/common")
    object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + "/", "xmlrpc/2/object")

    # Authenticate
    try:
        common = xmlrpc.client.ServerProxy(common_url)
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        if not uid:
            print("Authentication failed: check credentials.")
            sys.exit(1)
        print(f"Authenticated successfully. UID = {uid}")
    except Exception as e:
        print(f"Error during authentication: {e}")
        sys.exit(1)

    # Simple call: read name of the first res.partner (your contacts)
    try:
        models = xmlrpc.client.ServerProxy(object_url)
        partner_ids = models.execute_kw(DB, uid, PASSWORD,
            'res.partner', 'search', [[]], {'limit': 1})
        if not partner_ids:
            print("No partners found in the database.")
            return
        partner = models.execute_kw(DB, uid, PASSWORD,
            'res.partner', 'read', [partner_ids], {'fields': ['name']})
        print("First partner name:", partner[0]['name'])
    except Exception as e:
        print(f"Error calling Odoo method: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
