"""
Connect to Odoo using the provided RBAC testing credentials.
This script uses the XML-RPC API (odoo's standard remote API).

Requirements:
- Python 3
- "odoorpc" library (`pip install odoorpc`)

Usage:
    python connect_odoo_rbac.py
"""

import json
import sys

# Load credentials
with open('odoo_rbac_credentials.json') as f:
    creds = json.load(f)

url = creds['url']
dbname = creds['database']
username = creds['username']
password = creds['password']

# Odoo XML-RPC endpoints
import odoorpc

# Extract host and port from URL (default https port 443) and scheme
from urllib.parse import urlparse
parsed = urlparse(url)
host = parsed.hostname
port = parsed.port or (443 if parsed.scheme == 'https' else 80)
use_ssl = parsed.scheme == 'https'

# Connect
odoo = odoorpc.ODOO(host, port=port, protocol='jsonrpc' if use_ssl else 'xmlrpc')

# Authenticate
uid = odoo.env.authenticate(dbname, username, password, {})
if uid:
    print(f"Successfully authenticated to Odoo instance. UID: {uid}")
    # Example: list available models
    models = odoo.env['ir.model'].search([])
    print(f"Number of models available: {len(models)}")
else:
    print("Authentication failed.")
    sys.exit(1)
