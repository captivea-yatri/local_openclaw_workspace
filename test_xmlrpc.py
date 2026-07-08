import xmlrpc.client
import sys

url = sys.argv[1] if len(sys.argv) > 1 else "https://uriah-apolitical-masako.ngrok-free.dev"
db = sys.argv[2] if len(sys.argv) > 2 else "odoo19_captivea2"
username = sys.argv[3] if len(sys.argv) > 3 else "admin1"
password = sys.argv[4] if len(sys.argv) > 4 else "a"

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
try:
    uid = common.authenticate(db, username, password, {})
    print(f"Authenticated uid: {uid}")
except Exception as e:
    print(f"Authentication failed: {e}")
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
try:
    # Test calling a method
    version = models.execute_kw(db, uid, password, 'ir.config_parameter', 'get_param', ['database.version'])
    print(f"Odoo version: {version}")
except Exception as e:
    print(f"Error calling method: {e}")
