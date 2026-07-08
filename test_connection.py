import xmlrpc.client
import sys

url = sys.argv[1] if len(sys.argv) > 1 else 'https://b976-2402-a00-152-5177-2cba-11f3-a241-d7fc.ngrok-free.app'
db = sys.argv[2] if len(sys.argv) > 2 else 'odoo19_captivea2'
login = sys.argv[3] if len(sys.argv) > 3 else 'admin1'
password = sys.argv[4] if len(sys.argv) > 4 else 'a'

print(f'Testing connection to {url} db={db} login={login}')
try:
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, login, password, {})
    print(f'Authentication succeeded. UID: {uid}')
except Exception as e:
    print(f'Authentication failed: {e}')
    sys.exit(1)