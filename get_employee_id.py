import json, urllib.request, sys
url = "https://uriah-apolitical-masako.ngrok-free.dev/jsonrpc"
uid = None
# Authenticate
auth_payload = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {"service": "common", "method": "authenticate", "args": ["odoo19_captivea2", "admin1", "a", {}]},
    "id": 1,
}
req = urllib.request.Request(url, data=json.dumps(auth_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=10)
uid = json.loads(resp.read().decode('utf-8')).get('result')
print('uid', uid)
# Search employee
search_payload = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {"service": "object", "method": "execute_kw", "args": ["odoo19_captivea2", uid, "a", "hr.employee", "search", [[('name','=', 'RPC Quality Test Employee')]], {}]},
    "id": 2,
}
req = urllib.request.Request(url, data=json.dumps(search_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=10)
ids = json.loads(resp.read().decode('utf-8')).get('result')
print('employee ids', ids)
