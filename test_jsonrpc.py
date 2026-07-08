import json
import urllib.request
import urllib.error

url = "https://uriah-apolitical-masako.ngrok-free.dev/jsonrpc"
data = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "service": "common",
        "method": "authenticate",
        "args": ["odoo19_captivea2", "admin1", "a", {}]
    },
    "id": 1
}
data_bytes = json.dumps(data).encode('utf-8')
req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp_data = json.loads(resp.read().decode('utf-8'))
        print("Response:", resp_data)
except Exception as e:
    print("Error:", e)
