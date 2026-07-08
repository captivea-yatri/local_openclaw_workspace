import xmlrpc.client
import sys

url = 'https://uriah-apolitical-masako.ngrok-free.dev'
db = 'odoo19_captivea2'
username = 'admin1'
password = 'a'

common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
uid = None
try:
    uid = common.authenticate(db, username, password, {})
except Exception as e:
    print('Authentication failed:', e)
    sys.exit(1)

if uid:
    print('Authenticated successfully. UID:', uid)
    # Example: read partner names
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
    partners = models.execute_kw(db, uid, password, 'res.partner', 'search_read', [[]], {'fields': ['name'], 'limit': 5})
    print('First 5 partners:', partners)
else:
    print('Authentication returned None')
