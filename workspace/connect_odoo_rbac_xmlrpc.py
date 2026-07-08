"""
Connect to Odoo using the provided RBAC testing credentials via XML-RPC.
No external dependencies required; uses Python's built-in xmlrpc.client.
"""

import json
import sys
from urllib.parse import urlparse
import xmlrpc.client

# Load credentials
with open('odoo_rbac_credentials.json') as f:
    creds = json.load(f)

url = creds['url']
dbname = creds['database']
username = creds['username']
password = creds['password']

# Parse URL to get host and port
parsed = urlparse(url)
host = parsed.hostname
port = parsed.port or (443 if parsed.scheme == 'https' else 80)
use_ssl = parsed.scheme == 'https'

# Build XML-RPC endpoints
common_path = '/xmlrpc/2/common'
object_path = '/xmlrpc/2/object'

protocol = 'https' if use_ssl else 'http'
common_url = f"{protocol}://{host}:{port}{common_path}"
object_url = f"{protocol}://{host}:{port}{object_path}"

# Connect to common endpoint
common = xmlrpc.client.ServerProxy(common_url)

# Authenticate
uid = common.authenticate(dbname, username, password, {})
if not uid:
    print('Authentication failed.')
    sys.exit(1)
print(f'Authenticated successfully. UID: {uid}')

# Connect to object endpoint for further calls (example: list models)
objects = xmlrpc.client.ServerProxy(object_url)

# Example: get model count for ir.model
model_ids = objects.execute_kw(dbname, uid, password,
                              'ir.model', 'search', [[]])
print(f'Number of models available: {len(model_ids)}')
